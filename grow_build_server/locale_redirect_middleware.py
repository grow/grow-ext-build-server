import os


class LocaleRedirectMiddleware(object):

    def __init__(self, app, root, locales=None, default_locale=None):
        self.app = app
        self.root = root
        self.default_locale = default_locale
        if self.default_locale:
            self.default_locale = self.default_locale.lower()
        self.locales = locales or []
        self.locales = [locale.lower() for locale in self.locales]
        self.territories_to_identifiers = {}
        for locale in self.locales:
            territory = locale.split('_')[-1]
            territory = territory.lower()
            self.territories_to_identifiers[territory] = locale

    def redirect(self, locale_start_response, url):
        if url.endswith('/index.html'):
            url = url[:-11]
        url = '/{}'.format(url)
        status = '302 Found'
        response_headers = [('Location', url)]
        locale_start_response(status, response_headers)
        return []

    def __call__(self, environ, start_response):
        # Extract territory from URL. If the URL is localized, return.
        # If it's not localized, check if a cookie is set.
        # If a cookie is set already, don't do anything and serve the app.
        # If no cookie, determine if there's a file on disk that matches
        # the locale, set the cookie, and redirect.
        url_path = environ['PATH_INFO'].lstrip('/')
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

        if not url_path:
            url_path = 'index.html'
        if url_path.endswith('/'):
            url_path += '/index.html'
        root_path_on_disk = os.path.join(self.root, url_path)
        localized_path_on_disk = None
        if locale_from_header:
            localized_path_on_disk = os.path.join(
                    self.root, locale_from_header, url_path)

        # If no file is found at the current location, and if we have a file at
        # a path corresponding to the default locale, redirect.
        if self.default_locale:
            default_localized_path_on_disk = os.path.join(
                    self.root, self.default_locale, url_path)
            if not os.path.exists(root_path_on_disk) \
                    and os.path.exists(default_localized_path_on_disk):
                url = os.path.join(self.default_locale, url_path)
                return self.redirect(locale_start_response, url)

        # Redirect the user if we have a localized file.
        if locale_from_header and os.path.exists(localized_path_on_disk):
            url = os.path.join(locale_from_header, url_path)
            return self.redirect(locale_start_response, url)

        # Do nothing if user is in a country we don't have.
        return self.app(environ, locale_start_response)
