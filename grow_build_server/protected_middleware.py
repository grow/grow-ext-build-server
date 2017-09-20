from google.appengine.ext import ndb
import google_sheets
import logging
import mimetypes
import os
import re
import users
import webapp2


class ProtectedPath(ndb.Model):
    path = ndb.StringProperty()
    sheet_id = ndb.StringProperty()
    sheet_gid = ndb.StringProperty()


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
        sheet_id, sheet_gid, is_protected = \
                users.get_protected_information(
                        self.protected_paths, path_from_url)
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

        protected_sheet = google_sheets.get_sheet(sheet_id, gid=sheet_gid)
        if user.can_read(protected_sheet, None):
            return self.app(environ, start_response)
        # User is forbidden.
        logging.info('Using sheet id -> {}'.format(sheet_id))
        logging.info('Using sheet gid -> {}'.format(sheet_gid))
        status = '403 Forbidden'
        response_headers = [('X-Reason', 'No folder-level access.')]
        start_response(status, response_headers)
        return []


class CacheSheetsHandler(webapp2.RequestHandler):

    def get(self):
        protected_paths = self.app.config.get('protected_paths', [])
        for path in protected_paths:
            sheet_id = path['sheet_id']
            sheet_gid = path['sheet_gid']
            try:
                google_sheets.get_sheet(sheet_id, gid=sheet_gid, use_cache=False)
                logging.info('Successfully cached Google Sheet -> {}:{}'.format(sheet_id, sheet_gid))
                self.response.out.write('Cached -> {}:{}\n'.format(sheet_id, sheet_gid))
            except google_sheets.Error as error:
                logging.error('Failed to cache sheet -> {}'.format(str(error)))
                self.response.out.write('Failed -> {}:{}\n'.format(sheet_id, sheet_gid))
