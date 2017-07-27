from locale_redirect_middleware import LocaleRedirectMiddleware
from static_file_server_app import StaticFileServerApplication
from sheets_auth_middleware import SheetsAuthMiddleware
from protorpc.wsgi import service
import access_requests
import cors
import search_app
import logging
import os
import yaml
import webapp2

DEFAULT_DIR = os.getenv('GROW_BUILD_DIR', 'build')

# Get default locales from podspec, if it exists.
podspec_path = os.path.join(os.path.dirname(__file__), '..', '..', 'podspec.yaml')
podspec_path = os.path.abspath(podspec_path)
if not os.path.exists(podspec_path):
    locales = []
    default_locale = None
    build_server_config = {}
    static_paths = []
else:
    podspec = yaml.load(open(podspec_path))
    locales = podspec.get('localization', {}).get('locales', [])
    default_locale = podspec.get('localization', {}).get('default_locale')
    build_server_config = podspec.get('build_server', {})
    static_paths = []
    for static_dir in podspec.get('static_dirs', []):
        static_paths.append(static_dir['serve_at'])

logging.info('Using locales -> {}'.format(', '.join(locales)))
logging.info('Using default locale -> {}'.format(default_locale))

# Set build root.
root = os.path.join(os.path.dirname(__file__), '..', '..', DEFAULT_DIR)
root = os.path.abspath(root)

build_server_config['root'] = root
build_server_config['locales'] = locales

backend = webapp2.WSGIApplication([
    access_requests.FormResponseHandler.mapping(),
    ('/_grow/acl/approve/(.*)', access_requests.ApproveAccessRequestHandler),
    ('/_grow/search/index', search_app.IndexHandler),
    ('/_ah/warmup', search_app.IndexHandler),
], config=build_server_config)

_static_app = StaticFileServerApplication(root=root)
_locale_app = LocaleRedirectMiddleware(
        _static_app, root=root, locales=locales,
        default_locale=default_locale)
app = SheetsAuthMiddleware(
        _locale_app, static_paths=static_paths,
        config=build_server_config)

api = cors.CorsMiddleware(service.service_mappings((
    ('/_grow/api/search.*', search_app.SearchService),
)))
