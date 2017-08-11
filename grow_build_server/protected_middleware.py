from google.appengine.ext import ndb
import google_sheets
import mimetypes
import os
import re
import users


class ProtectedPath(ndb.Model):
    path = ndb.StringProperty()
    sheet_id = ndb.StringProperty()
    sheet_gid = ndb.StringProperty()


def get_protected_sheet():
    settings = google_sheets.Settings.instance()
    sheet_id = settings.sheet_id
    sheet_gid_protected = settings.sheet_gid_protected
    return google_sheets.get_sheet(sheet_id, gid=sheet_gid_protected)


class ProtectedMiddleware(object):

    def __init__(self, app, config):
        self.app = app
        self.protected_paths = config.get('protected_paths', [])
        self.sign_in_path = config.get('access_requests', {}).get('request_access_path')

    def redirect(self, url, start_response):
        status = '302 Found'
        response_headers = [('Location', url)]
        start_response(status, response_headers)
        return []

    def __call__(self, environ, start_response):
        if not self.protected_paths:
            return self.app(environ, start_response)
        path_from_url = environ['PATH_INFO']
        is_protected = False
        for path_regex in self.protected_paths:
            if re.match(path_regex, path_from_url):
                is_protected = True
        if not is_protected:
            return self.app(environ, start_response)

        user = users.User.get_from_environ()
        # User is unauthorized.
        if user is None:
            if self.sign_in_path:
                url = '{}?next={}'.format(self.sign_in_path, path_from_url)
                return self.redirect(url, start_response)
            else:
                status = '401 Unauthorized'
                response_headers = []
                start_response(status, response_headers)
                return []

        # TODO: Multiple sheets.
        protected_sheet = get_protected_sheet()
        # User is forbidden.
        if user.can_read(protected_sheet, None):
            return self.app(environ, start_response)
        status = '403 Forbidden'
        response_headers = []
        start_response(status, response_headers)
        return []
