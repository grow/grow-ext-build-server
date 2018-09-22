from protorpc import messages
from protorpc import remote
from google.appengine.ext.ndb import msgprop
from protorpc import message_types
import config
import Cookie
import config as config_lib
import google.auth.transport.requests
import google.oauth2.id_token
import google_sheets
import logging
import os
import re
import yaml
from google.appengine.api import users as api_users
from google.appengine.ext import ndb
from google.appengine.datastore import datastore_query

HTTP_REQUEST = google.auth.transport.requests.Request()
COOKIE_NAME = os.getenv('FIREBASE_TOKEN_COOKIE', 'firebaseToken')
REFRESH_COOKIE_NAME = os.getenv('FIREBASE_REFRESH_TOKEN_COOKIE', 'firebaseRefreshToken')


def _list_folders():
    pod_root = os.path.join(os.path.dirname(__file__), '..', '..')
    path = os.path.join(pod_root, 'build-server-config.yaml')
    path = os.path.abspath(path)
    return yaml.load(open(path))['folders']


FOLDERS = _list_folders()


class FolderMessage(messages.Message):
    folder_id = messages.StringField(1)
    title = messages.StringField(2)
    has_access = messages.BooleanField(3, default=False)
    has_requested = messages.BooleanField(4, default=False)
    is_locked = messages.BooleanField(6)
    regex = messages.StringField(5)


class QuestionMessage(messages.Message):
    question = messages.StringField(1)
    answer = messages.StringField(2)


class FolderStatus(messages.Enum):
    ALL_APPROVED = 1
    SOME_REQUESTED = 2


class UserMessage(messages.Message):
    email = messages.StringField(1)
    domain = messages.StringField(2)
    created = message_types.DateTimeField(3)
    created_by = messages.StringField(4)
    modified = message_types.DateTimeField(5)
    modified_by = messages.StringField(6)
    num_folders = messages.IntegerField(7)
    folders = messages.MessageField(FolderMessage, 8, repeated=True)
    folder_status = messages.EnumField(FolderStatus, 9)
    questions = messages.MessageField(QuestionMessage, 10, repeated=True)
    reason = messages.StringField(11)


def get_protected_information(protected_paths, path_from_url):
    # TODO: Move configuration to UI.
    for item in protected_paths:
        path_regex = item['regex']
        if re.match(path_regex, path_from_url):
            sheet_id = item['sheet_id']
            sheet_gid = item['sheet_gid']
            return sheet_id, sheet_gid, True
    return (None, None, False)


def get_cookie_value(name):
    cookie = Cookie.SimpleCookie(os.getenv('HTTP_COOKIE'))
    morsel = cookie.get(name)
    if not morsel:
        return
    return morsel.value


class PersistentUser(ndb.Model):
    email = ndb.StringProperty()
    domain = ndb.StringProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)
    modified = ndb.DateTimeProperty(auto_now=True)
    modified_by = ndb.StringProperty()
    created_by = ndb.StringProperty()
    num_folders = ndb.IntegerProperty()
    is_wildcard = ndb.BooleanProperty()
    folders = msgprop.MessageProperty(FolderMessage, repeated=True)
    folder_status = msgprop.EnumProperty(FolderStatus)
    questions = msgprop.MessageProperty(QuestionMessage, repeated=True)
    reason = ndb.TextProperty()

    def _pre_put_hook(self):
        if self.email:
            self.email = self.email.strip().lower()
            self.domain = self.email.split('@')[-1]
            self.is_wildcard = self.email[0] == '*'
        if self.created_by:
            self.created_by = self.created_by.strip().lower()
        if self.modified_by:
            self.modified_by = self.modified_by.strip().lower()
        if self.folders:
            folder_status = FolderStatus.ALL_APPROVED
            for folder in self.folders:
                if folder.has_requested:
                    folder_status = FolderStatus.SOME_REQUESTED
            self.folder_status = folder_status
            self.num_folders = len([folder for folder in self.folders
                                    if folder.has_access])

    @classmethod
    def search(cls, query_string=None, cursor=None, limit=None):
        limit = limit or 200
        start_cursor = datastore_query.Cursor(urlsafe=cursor) \
                if cursor else None
        query = cls.query()
        if query_string:
            # TODO: Support query language.
            query = query.filter(cls.email == query_string)
        query = query.order(-cls.created)
        results, next_cursor, has_more = \
                query.fetch_page(limit, start_cursor=start_cursor)
        return (results, next_cursor, has_more)

    @classmethod
    def normalize_email(cls, email):
        return email.strip().lower().replace(' ', '')

    def can_read(self, path_from_url):
        # When FOLDERS have changed after the user was added.
        # This should be moved to when PersistentUser is instantiated.
        self.folders = self.normalize_folders()
        for folder in self.folders:
            path_regex = folder.regex
            if re.match(path_regex, path_from_url):
                if not folder.has_access:
                    return False
        return True

    def normalize_folders(self):
        ids_to_folders = {}
        all_folders = list_folder_messages()
        for folder in all_folders:
            ids_to_folders[folder.folder_id] = folder
        for folder in self.folders:
            # Old folder no longer used.
            if folder.folder_id not in ids_to_folders:
                continue
            ids_to_folders[folder.folder_id].has_access = folder.has_access
            ids_to_folders[folder.folder_id].has_requested = folder.has_requested
        all_folders = ids_to_folders.values()
        return sorted(all_folders, key=lambda folder: folder.title)

    @classmethod
    def import_from_sheets(cls, sheet_id, sheet_gid, folders=None,
                           created_by=None, remove_access=False):
        rows = google_sheets.get_sheet(sheet_id, gid=sheet_gid)
        emails = [row['email'] for row in rows]
        if not folders:
            folders = list_folder_messages(default_has_access=True)
        return cls.create_or_update_multi(
                emails, folders=folders, created_by=created_by,
                remove_access=remove_access)

    @classmethod
    def to_csv(cls):
        # TODO: Move to separate file.
        from protorpc import protojson
        import io
        import csv
        import json
        _csv_header = [
            'created',
            'email',
            'folders',
        ]
        header = _csv_header
        ents, _, _ = cls.search(limit=5000)
        rows = []
        for ent in ents:
            row = json.loads(protojson.encode_message(ent.to_message()))
            for key in row.keys():
                if key not in header:
                    del row[key]
            for key in row:
                if key == 'folders':
                    row[key] = json.dumps(row[key])
                if isinstance(row[key], unicode):
                    row[key] = row[key].encode('utf-8')
            rows.append(row)
        if not rows:
            return ''
        fp = io.BytesIO()
        writer = csv.DictWriter(fp, header)
        writer.writeheader()
        writer.writerows(rows)
        fp.seek(0)
        return fp.read()

    @classmethod
    def create(cls, email, folders=None, created_by=None):
        user = cls._create(email, folders, created_by)
        user.put()
        return user

    @classmethod
    def _create(cls, email, folders=None, created_by=None):
        email = cls.normalize_email(email)
        key = ndb.Key('PersistentUser', email)
        user = cls(key=key)
        user.email = email
        if folders:
            user.folders = folders
        else:
            user.folders = list_folder_messages()
        user.created_by = created_by
        user.modified_by = created_by
        return user

    def add_folders(self, folders, remove_access=False):
        should_have_access = not remove_access
        ids_to_folders = {}
        for folder in self.normalize_folders():
            ids_to_folders[folder.folder_id] = folder
        for folder in folders:
            if folder.has_access and folder.folder_id in ids_to_folders:
                ids_to_folders[folder.folder_id].has_access = should_have_access
        all_folders = ids_to_folders.values()
        all_folders = sorted(all_folders, key=lambda folder: folder.title)
        self.folders = all_folders

    @classmethod
    def create_or_update_multi(cls, emails, folders=None, created_by=None, remove_access=False):
        keys = [ndb.Key('PersistentUser', cls.normalize_email(email)) for email in emails if email]
        ents = ndb.get_multi(keys)
        for i, ent in enumerate(ents):
            if not ent:
                ents[i] = cls._create(emails[i], folders=folders, created_by=created_by)
                continue
            ent.add_folders(folders, remove_access=remove_access)
        ndb.put_multi(ents)
        return ents

    @classmethod
    def create_multi(cls, emails, folders=None, created_by=None):
        ents = [cls._create(email, folders=folders, created_by=created_by)
                for email in emails]
        ndb.put_multi(ents)
        return ents

    @classmethod
    def get(cls, email):
        email = cls.normalize_email(email)
        key = ndb.Key('PersistentUser', email)
        return key.get()

    @classmethod
    def get_by_email(cls, email):
        email = cls.normalize_email(email)
        key = ndb.Key('PersistentUser', email)
        return key.get()

    @classmethod
    def get_or_create(cls, email):
        ent = cls.get(email)
        return ent or cls.create(email)

    def delete(self):
        self.key.delete()

    def to_message(self):
        message = UserMessage()
        message.created_by = self.created_by
        message.modified_by = self.modified_by
        message.created = self.created
        message.domain = self.domain
        message.email = self.email
        if self.folders:
            message.folders = self.normalize_folders()
        message.folder_status = self.folder_status
        message.modified = self.modified
        message.num_folders = self.num_folders
        if self.questions:
            message.questions = self.questions
        if self.reason:
            message.reason = self.reason
        return message

    def request_access(self, folders, questions=None,
                       reason=None,
                       send_notification=False):
        if questions:
            self.questions = questions
        if reason:
            self.reason = reason
        all_folders = self.normalize_folders()
        requested_folder_ids = [folder.folder_id for folder in folders]
        for i, folder in enumerate(all_folders):
            is_requested = folder.folder_id in requested_folder_ids
            # Set newly-requested folders while leaving previously requested
            # folders as-is.
            if is_requested:
                all_folders[i].has_requested = is_requested
        self.folders = all_folders
        self.put()
        if send_notification:
            build_server_config = config.instance()
            email_config = build_server_config['access_requests']['emails']
            req = {
                'email': self.email,
                'form': questions,
            }
            from . import access_requests
            access_requests.send_email_to_admins(req, email_config=email_config)

    def update_folders(self, folders, updated_by=None):
        self.folders = folders
        if updated_by:
            self.updated_by = updated_by
        self.put()


class User(object):

    def __init__(self, data):
        for key, value in data.iteritems():
            setattr(self, key, value)

    def __repr__(self):
        return '<User {}>'.format(self.email)

    @property
    def domain(self):
        return self.email.split('@')[-1]

    @classmethod
    def refresh_firebase_token(cls):
        firebase_token = get_cookie_value(COOKIE_NAME)
        refresh_token = get_cookie_value(REFRESH_COOKIE_NAME)
        if not refresh_token or not firebase_token:
            return

    def get_persistent(self):
        return PersistentUser.get_by_email(self.email)

    @classmethod
    def get_from_environ(cls):
        firebase_token = get_cookie_value(COOKIE_NAME)
        if not firebase_token:
            return
        try:
            claims = google.oauth2.id_token.verify_firebase_token(
                            firebase_token, HTTP_REQUEST)
            return cls(claims)
        except ValueError as e:
            if 'Token expired' in str(e):
                logging.info('Firebase token expired.')
            else:
                logging.info('Problem with Firebase token -> {}'.format(str(e)))

    def can_admin(self, sheet):
        return self.can_read(sheet)

    def can_read(self, sheet, path=None):
        for row in sheet:
            if self.email.lower() == row.get('email', '').lower().strip() \
                    or self.domain == row.get('domain', '').lower().strip():
                return True
        return False

    def to_message(self):
        message = UserMessage()
        message.email = self.email
        message.domain = self.domain
        return message


def list_folder_messages(default_has_access=False):
    folders = []
    for folder in FOLDERS:
        has_access = default_has_access and 'Archive' not in folder['title']
        folders.append(FolderMessage(
            folder_id=folder['folder_id'],
            title=folder['title'],
            regex=folder['regex'],
            has_access=has_access))
    folders = sorted(folders, key=lambda folder: folder.title)
    return folders


class GetMeRequest(messages.Message):
    pass


class GetMeResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class CanReadRequest(messages.Message):
    path = messages.StringField(1)


class CanReadResponse(messages.Message):
    can_read = messages.BooleanField(1)


class CanAdminRequest(messages.Message):
    pass


class CanAdminResponse(messages.Message):
    can_admin = messages.BooleanField(1)


class DeleteUserRequest(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class DeleteUserResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class GetUserRequest(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class GetUserResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class UpdateUserRequest(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class UpdateUserResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class CreateUserRequest(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class CreateUserResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class SearchUsersRequest(messages.Message):
    next_cursor = messages.StringField(1)
    query = messages.StringField(2)


class SearchUsersResponse(messages.Message):
    users = messages.MessageField(UserMessage, 1, repeated=True)
    next_cursor = messages.StringField(2)
    has_more = messages.BooleanField(3)


class ImportFromSheetsRequest(messages.Message):
    sheet_id = messages.StringField(1)
    sheet_gid = messages.StringField(2)
    folders = messages.MessageField(FolderMessage, 3, repeated=True)
    remove_access = messages.BooleanField(4)


class ImportFromSheetsResponse(messages.Message):
    num_imported = messages.IntegerField(1)


class RequestAccessRequest(messages.Message):
    folders = messages.MessageField(FolderMessage, 1, repeated=True)
    questions = messages.MessageField(QuestionMessage, 2, repeated=True)
    email = messages.StringField(3)
    reason = messages.StringField(4)


class RequestAccessResponse(messages.Message):
    pass


class UsersService(remote.Service):

    @property
    def me(self):
        return api_users.get_current_user().email()

    @remote.method(CanAdminRequest, CanAdminResponse)
    def can_admin(self, request):
        instance = google_sheets.Settings.instance()
        sheet_id = instance.sheet_id
        sheet_gid_admins = instance.sheet_gid_admins
        protected_sheet = \
                google_sheets.get_sheet(sheet_id, gid=sheet_gid_admins)
        user = User.get_from_environ()
        can_admin = user and user.can_admin(protected_sheet)
        resp = CanAdminResponse()
        resp.can_admin = can_admin
        return resp

    @remote.method(CanReadRequest, CanReadResponse)
    def can_read(self, request):
        user = User.get_from_environ()
        persistent_user = user.get_persistent()
        can_read = persistent_user \
                and persistent_user.can_read(request.path)
        resp = CanReadResponse()
        resp.can_read = can_read
        return resp

    @remote.method(GetMeRequest, GetMeResponse)
    def get_me(self, request):
        user = User.get_from_environ()
        resp = GetMeResponse()
        if user:
            resp.user = user.to_message()
        return resp

    @remote.method(CreateUserRequest, CreateUserResponse)
    def create(self, request):
        user = PersistentUser.create(
                request.user.email, created_by=self.me)
        resp = CreateUserResponse()
        resp.user = user.to_message()
        return resp

    @remote.method(DeleteUserRequest, DeleteUserResponse)
    def delete(self, request):
        user = PersistentUser.get(request.user.email)
        if user:
            user.delete()
        resp = DeleteUserResponse()
        return resp

    @remote.method(SearchUsersRequest, SearchUsersResponse)
    def search(self, request):
        query = request.query
        users, next_cursor, has_more = PersistentUser.search(query)
        resp = SearchUsersResponse()
        resp.users = [user.to_message() for user in users]
        resp.has_more = has_more
        if next_cursor:
            resp.next_cursor = next_cursor.urlsafe()
        return resp

    @remote.method(UpdateUserRequest, UpdateUserResponse)
    def update(self, request):
        user = PersistentUser.get(request.user.email)
        user.update_folders(request.user.folders, updated_by=self.me)
        resp = UpdateUserResponse()
        resp.user = user.to_message() if user else None
        return resp

    @remote.method(GetUserRequest, GetUserResponse)
    def get(self, request):
        user = PersistentUser.get(request.user.email)
        resp = GetUserResponse()
        resp.user = user.to_message() if user else None
        return resp

    @remote.method(GetUserRequest, GetUserResponse)
    def send_email_notification(self, request):
        build_server_config = config.instance()
        email_config = build_server_config['access_requests']['emails']
        user = PersistentUser.get(request.user.email)
        email = user.email
        kwargs = {
            'folders': user.folders,
        }
        from . import access_requests
        access_requests.send_email_to_existing_user(
                email, email_config, kwargs)
        resp = GetUserResponse()
        return resp

    @remote.method(ImportFromSheetsRequest, ImportFromSheetsResponse)
    def import_from_sheets(self, request):
        sheet_id = request.sheet_id
        sheet_gid = request.sheet_gid
        ents = PersistentUser.import_from_sheets(
            sheet_id=sheet_id, sheet_gid=sheet_gid,
            folders=request.folders,
            created_by=self.me,
            remove_access=request.remove_access)
        resp = ImportFromSheetsResponse()
        resp.num_imported = len(ents)
        return resp

    @remote.method(RequestAccessRequest, RequestAccessResponse)
    def request_access(self, request):
        user = PersistentUser.get_or_create(request.email)
        user.request_access(
                request.folders,
                questions=request.questions,
                reason=request.reason,
                send_notification=True)
        resp = RequestAccessResponse()
        return resp
