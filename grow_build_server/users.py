from protorpc import messages
from protorpc import remote
import Cookie
import google.auth.transport.requests
import google.oauth2.id_token
import google_sheets
import logging
import os

HTTP_REQUEST = google.auth.transport.requests.Request()
COOKIE_NAME = os.getenv('FIREBASE_TOKEN_COOKIE', 'firebaseToken')


def get_protected_sheet():
    settings = google_sheets.Settings.instance()
    sheet_id = settings.sheet_id
    sheet_gid_protected = settings.sheet_gid_protected
    return google_sheets.get_sheet(sheet_id, gid=sheet_gid_protected)


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

    def can_read(self, sheet, path):
        for row in sheet:
            if self.email.lower() == row.get('email', '').lower() \
                    or self.domain == row.get('domain', '').lower():
                return True
        return False


class CanReadRequest(messages.Message):
    path = messages.StringField(1)


class CanReadResponse(messages.Message):
    can_read = messages.BooleanField(1)


class UsersService(remote.Service):

    @remote.method(CanReadRequest, CanReadResponse)
    def can_read(self, request):
        protected_sheet = get_protected_sheet()  # TODO: Multiple sheets.
        user = User.get_from_environ()
        if not user:
            can_read = False
        else:
            can_read = user.can_read(protected_sheet, request.path)
        resp = CanReadResponse()
        resp.can_read = can_read
        return resp
