import logging
import os
import yaml

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

# Set build root.
root = os.path.join(os.path.dirname(__file__), '..', '..', DEFAULT_DIR)
root = os.path.abspath(root)

build_server_config['default_locale'] = default_locale
build_server_config['static_paths'] = static_paths
build_server_config['root'] = root
build_server_config['locales'] = locales

def instance():
    locales = build_server_config['locales']
    default_locale = build_server_config['default_locale']
    logging.info('Using locales -> {}'.format(', '.join(locales)))
    logging.info('Using default locale -> {}'.format(default_locale))
    return build_server_config
