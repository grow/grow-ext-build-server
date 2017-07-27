class CorsMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            headers.append(('Access-Control-Allow-Origin', '*'))
            headers.append(('Access-Control-Request-Headers', 'Content-Type'))
            return start_response(status, headers, exc_info)
        if environ.get('REQUEST_METHOD') == 'OPTIONS':
            status = '200 OK'
            return custom_start_response(status, [])
        return self.app(environ, custom_start_response)
