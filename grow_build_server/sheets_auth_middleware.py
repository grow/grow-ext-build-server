from google.appengine.ext import vendor
vendor.add('extensions')

from requests_toolbelt.adapters import appengine
appengine.monkeypatch()

import google_sheets
import users

REDIRECT_TO_SHEETS_PATH = '/_grow/acl'


class SheetsAuthMiddleware(object):

    def __init__(self, app, config, static_paths, unprotected_paths=None):
        self.app = app
        self.errors = config.get('error_pages', [])
        self.admins = config.get('admins', [])
        access_requests = config.get('access_requests', {})
        self.request_access_path = access_requests.get('sign_in_path')
        self.sign_in_path = access_requests.get('request_access_path')
        self.title = config.get('title', 'Untitled Site')
        self.redirect_to_sheet_path = REDIRECT_TO_SHEETS_PATH
        self.static_paths = static_paths
        self.unprotected_paths = unprotected_paths or []
        if self.static_paths:
            self.unprotected_paths += self.static_paths
        if self.request_access_path:
            self.unprotected_paths.append(self.request_access_path)
        if self.sign_in_path:
            self.unprotected_paths.append(self.sign_in_path)

    def redirect(self, url, start_response):
        status = '302 Found'
        response_headers = [('Location', url)]
        start_response(status, response_headers)
        return []

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO']
        # Static dirs are unprotected.
        if self.unprotected_paths:
            for dir_path in self.unprotected_paths:
                if path.startswith(dir_path):
                    return self.app(environ, start_response)

        user = users.User.get_from_environ()
        persistent_user = user and user.get_persistent()

        # Redirect to the sign in page if not signed in.
        if not user or not persistent_user:
            if self.sign_in_path:
                url = '{}?next={}'.format(self.sign_in_path, path)
                return self.redirect(url, start_response)
            else:
                status = '401 Unauthorized'
                response_headers = []
                start_response(status, response_headers)
                return []

        has_access = persistent_user.can_read(path)

        # If the user is on the register page and if they have access,
        # redirect them to the homepage.
        if path in [self.sign_in_path, self.request_access_path] and has_access:
            self.redirect('/', start_response)
            return []

        if not has_access:
            if self.request_access_path:
                url = self.request_access_path
                return self.redirect(url, start_response)
            else:
                status = '403 Forbidden'
                response_headers = [('X-Reason', 'No site-level access.')]
                start_response(status, response_headers)
                return []

        return self.app(environ, start_response)
