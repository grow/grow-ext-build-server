class CorsMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            headers.append(('Access-Control-Allow-Origin', '*'))
            return start_response(status, headers, exc_info)
        return self.app(environ, custom_start_response)
