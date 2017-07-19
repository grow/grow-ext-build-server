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
else:
    podspec = yaml.load(open(podspec_path))
    locales = podspec.get('localization', {}).get('locales', [])

logging.info('Using locales -> {}'.format(', '.join(locales)))

# Set build root.
root = os.path.join(os.path.dirname(__file__), '..', '..', DEFAULT_DIR)
root = os.path.abspath(root)

_static_app = StaticFileServerApplication(root=root)
app = LocaleRedirectMiddleware(_static_app, root=root, locales=locales)
