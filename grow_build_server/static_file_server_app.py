import mimetypes
import os


class StaticFileServerApplication(object):

    def __init__(self, root):
        self.root = root

    def __call__(self, environ, start_response):
        path_from_url = environ['PATH_INFO'].lstrip('/')
        basename = os.path.basename(path_from_url)
        # /foo -> /foo/ redirect.
        if basename and '.' not in basename:
            status = '302 Found'
            url = '/{}/'.format(path_from_url)
            response_headers = [('Location', url)]
            start_response(status, response_headers)
            return []

        # /foo/ -> /foo/index.html
        path_on_disk = path_from_url
        if path_from_url.endswith('/'):
            path_on_disk = path_from_url + 'index.html'

        # Special case: /.
        if not path_from_url:
            path_on_disk = 'index.html'

        path_on_disk = os.path.join(self.root, path_on_disk)

        # 404.
        if not os.path.exists(path_on_disk):
            status = '404 Not Found'
            response_headers = []
            start_response(status, response_headers)
            return []

        status = '200 OK'
        mimetype = mimetypes.guess_type(path_on_disk)[0]
        response_headers = [('Content-Type', mimetype)]
        start_response(status, response_headers)
        content = open(path_on_disk).read()
        return [content]
