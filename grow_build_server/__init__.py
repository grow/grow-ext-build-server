from locale_redirect_middleware import LocaleRedirectMiddleware
from static_file_server_app import StaticFileServerApplication
import logging
import os
import yaml

DEFAULT_DIR = os.getenv('GROW_BUILD_DIR', 'build')

# Get default locales from podspec, if it exists.
podspec_path = os.path.join(os.path.dirname(__file__), '..', '..', 'podspec.yaml')
if not os.path.exists(podspec_path):
    locales = []
    default_locale = None
else:
    podspec = yaml.load(open(podspec_path))
    locales = podspec.get('localization', {}).get('locales', [])
    default_locale = podspec.get('localization', {}).get('default_locale')

logging.info('Using locales -> {}'.format(', '.join(locales)))
logging.info('Using default locale -> {}'.format(default_locale))

# Set build root.
root = os.path.join(os.path.dirname(__file__), '..', '..', DEFAULT_DIR)
root = os.path.abspath(root)

_static_app = StaticFileServerApplication(root=root)
app = LocaleRedirectMiddleware(
        _static_app, root=root, locales=locales,
        default_locale=default_locale)
