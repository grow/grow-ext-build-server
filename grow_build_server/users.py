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
from google.appengine.ext import ndb
from google.appengine.datastore import datastore_query

HTTP_REQUEST = google.auth.transport.requests.Request()
COOKIE_NAME = os.getenv('FIREBASE_TOKEN_COOKIE', 'firebaseToken')
REFRESH_COOKIE_NAME = os.getenv('FIREBASE_REFRESH_TOKEN_COOKIE', 'firebaseRefreshToken')


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
    created_by = ndb.StringProperty()
    folders = ndb.StringProperty(repeated=True)

    def _pre_put_hook(self):
        if self.email:
            self.email = self.email.strip().lower()
            self.domain = self.email.split('@')[-1]
        if self.created_by:
            self.created_by = self.created_by.strip().lower()
        if self.folders:
            self.folders = [folder.lower() for folder in self.folders]

    @classmethod
    def search(cls, cursor=None, limit=None):
        limit = limit or 200
        start_cursor = datastore_query.Cursor(urlsafe=cursor) if cursor else None
        query = cls.query()
        query = query.order(-cls.created)
        results, next_cursor, has_more = query.fetch_page(limit, start_cursor=start_cursor)
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
        message.email = self.email
        message.domain = self.domain
        return message


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


class UserMessage(messages.Message):
    email = messages.StringField(1)
    domain = messages.StringField(2)
    created = message_types.DateTimeField(3)


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


class CreateUserRequest(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class CreateUserResponse(messages.Message):
    user = messages.MessageField(UserMessage, 1)


class SearchUsersRequest(messages.Message):
    next_cursor = messages.StringField(1)


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
        user = PersistentUser.create(request.user.email)
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
        users, next_cursor, has_more  = PersistentUser.search()
        resp = SearchUsersResponse()
        resp.users = [user.to_message() for user in users]
        resp.has_more = has_more
        if next_cursor:
            resp.next_cursor = next_cursor.urlsafe()
        return resp
