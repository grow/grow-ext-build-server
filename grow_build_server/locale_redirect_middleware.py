import os


class LocaleRedirectMiddleware(object):

    def __init__(self, app, root, locales=None):
        self.app = app
        self.root = root
        self.locales = locales or []
        self.locales = [locale.lower() for locale in self.locales]
        self.territories_to_identifiers = {}
        for locale in self.locales:
            territory = locale.split('_')[-1]
            territory = territory.lower()
            self.territories_to_identifiers[territory] = locale

    def __call__(self, environ, start_response):
        # Extract territory from URL. If the URL is localized, return.
        # If it's not localized, check if a cookie is set.
        # If a cookie is set already, don't do anything and serve the app.
        # If no cookie, determine if there's a file on disk that matches
        # the locale, set the cookie, and redirect.
        url_path = environ['PATH_INFO'].strip('/')
        locale_part = url_path.split('/', 1)[0]
        locale_from_url = None
        territory_from_url = None

        # Do nothing if requesting a localized URL.
        if locale_part in self.locales:
            locale_from_url = locale_part
            territory_from_url = locale_from_url.split('_')[-1]
            def matched_locale_start_response(status, headers, exc_info=None):
                headers.append(('Grow-Build-Server-Locale', locale_part))
                return start_response(status, headers, exc_info)
            return self.app(environ, matched_locale_start_response)

        territory_from_header = environ.get('HTTP_X_APPENGINE_COUNTRY', '')
        territory_from_header = territory_from_header.lower()
        locale_from_header = \
                self.territories_to_identifiers.get(territory_from_header, '')
        locale_from_header = locale_from_header.lower()

        def locale_start_response(status, headers, exc_info=None):
            headers.append(('Grow-Build-Server-Locale', locale_from_header))
            headers.append(('Grow-Build-Server-Territory', territory_from_header))
            return start_response(status, headers, exc_info)

        # Do nothing if user is in a country we don't have.
        if not locale_from_header:
            return self.app(environ, locale_start_response)
        if not url_path:
            url_path = 'index.html'
        if url_path.endswith('/'):
            url_path += '/index.html'
        root_path_on_disk = os.path.join(self.root, url_path)
        localized_path_on_disk = os.path.join(
                self.root, locale_from_header, url_path)

        # Redirect the user if we have a localized file.
        if os.path.exists(localized_path_on_disk):
            url = os.path.join(locale_from_header, url_path)
            if url.endswith('/index.html'):
                url = url[:-11]
            status = '302 Found'
            response_headers = [('Location', url)]
            locale_start_response(status, response_headers)
            return []
        return self.app(environ, locale_start_response)
