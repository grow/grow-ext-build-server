import Cookie
import google.auth.transport.requests
import google.oauth2.id_token
import logging
import os

HTTP_REQUEST = google.auth.transport.requests.Request()
COOKIE_NAME = os.getenv('FIREBASE_TOKEN_COOKIE', 'firebaseToken')


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
            if self.email == row.get('email') \
                    or self.domain == row.get('domain'):
                return True
        return False
