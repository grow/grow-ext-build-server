from protorpc import messages
from protorpc import remote
import Cookie
import config as config_lib
import google.auth.transport.requests
import google.oauth2.id_token
import google_sheets
import logging
import os
import re

HTTP_REQUEST = google.auth.transport.requests.Request()
COOKIE_NAME = os.getenv('FIREBASE_TOKEN_COOKIE', 'firebaseToken')


def get_protected_information(protected_paths, path_from_url):
    # TODO: Move configuration to UI.
    for item in protected_paths:
        path_regex = item['regex']
        if re.match(path_regex, path_from_url):
            sheet_id = item['sheet_id']
            sheet_gid = item['sheet_gid']
            return sheet_id, sheet_gid, True
    return (None, None, False)


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
    def get_from_environ(cls):
        cookie = Cookie.SimpleCookie(os.getenv('HTTP_COOKIE'))
        morsel = cookie.get(COOKIE_NAME)
        if not morsel:
            return
        firebase_token = morsel.value
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
