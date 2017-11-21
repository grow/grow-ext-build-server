from protorpc import messages
from protorpc import remote
from google.appengine.ext.ndb import msgprop
from protorpc import message_types
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


class FolderMessage(messages.Message):
    folder_id = messages.StringField(1)
    title = messages.StringField(2)
    has_access = messages.BooleanField(3)
    has_requested = messages.BooleanField(4)


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
            self.num_folders = len(self.folders)
            folder_status = FolderStatus.ALL_APPROVED
            for folder in self.folders:
                if folder.has_requested:
                    folder_status = FolderStatus.SOME_REQUESTED
            self.folder_status = folder_status

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
        return email.strip().lower()

    @classmethod
    def create(cls, email, created_by=None):
        email = cls.normalize_email(email)
        key = ndb.Key('PersistentUser', email)
        user = cls(key=key)
        user.email = email
        user.created_by = created_by
        user.modified_by = created_by
        user.put()
        return user

    @classmethod
    def get(cls, email):
        key = ndb.Key('PersistentUser', email)
        return key.get()

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
            message.folders = self.folders
        message.folder_status = self.folder_status
        message.modified = self.modified
        message.num_folders = self.num_folders
        return message

    def request_access(self, folders):
        # Return if the folder is already requested or granted.
        if self.folders:
            for user_folder in self.folders:
                for folder in folders:
                    if user_folder == folder.folder_id:
                        return
        else:
            self.folders = []
        for folder in folders:
            message = FolderMessage(
                folder_id=folder.folder_id,
                has_requested=True)
            self.folders.append(message)
        self.put()

    def update_folders(self, folders):
        # TODO: Verify this doesn't clobber data.
        if self.folders:
            updated_folder_ids = [folder.folder_id for folder in folders]
            for i, folder in enumerate(self.folders):
                if folder.folder_id in updated_folder_ids:
                    del self.folders[i]
        new_folders = []
        for folder in folders:
            message = FolderMessage(
                folder_id=folder.folder_id,
                has_access=folder.has_access,
                has_requested=folder.has_requested)
            new_folders.append(message)
        self.folders = new_folders
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
                logging.exception('Problem with Firebase token.')

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


def list_folder_messages():
    folders = []
    data = yaml.load(open(os.path.join(os.path.dirname(__file__), 'folders.yaml')))
    for folder_id, title in data.iteritems():
        folder_id = str(folder_id)
        folders.append(FolderMessage(folder_id=folder_id, title=title))
    folders = sorted(folders, key=lambda folder: folder.title)
    return folders


class MeRequest(messages.Message):
    pass


class MeResponse(messages.Message):
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


class UsersService(remote.Service):

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
        config = config_lib.instance()
        protected_paths = config.get('protected_paths', [])
        sheet_id, sheet_gid, is_protected = \
                get_protected_information(
                        protected_paths, request.path)
        protected_sheet = \
                google_sheets.get_sheet(sheet_id, gid=sheet_gid)
        user = User.get_from_environ()
        can_read = user and user.can_read(protected_sheet, request.path)
        resp = CanReadResponse()
        resp.can_read = can_read
        return resp

    @remote.method(MeRequest, MeResponse)
    def me(self, request):
        user = User.get_from_environ()
        resp = MeResponse()
        if user:
            resp.user = user.to_message()
        return resp

    @remote.method(CreateUserRequest, CreateUserResponse)
    def create(self, request):
        created_by = api_users.get_current_user().email()
        user = PersistentUser.create(
                request.user.email, created_by=created_by)
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
        user.update_folders(request.user.folders)
        resp = UpdateUserResponse()
        resp.user = user.to_message() if user else None
        return resp

    @remote.method(GetUserRequest, GetUserResponse)
    def get(self, request):
        user = PersistentUser.get(request.user.email)
        resp = GetUserResponse()
        resp.user = user.to_message() if user else None
        return resp
