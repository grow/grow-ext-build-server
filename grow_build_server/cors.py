def CorsMiddleware(app):

    def _set_headers(headers):
        headers.append(('Access-Control-Allow-Origin', '*'))
        headers.append(('Access-Control-Allow-Methods', '*'))
        headers.append(('Access-Control-Allow-Headers', 'origin, content-type, accept'))
        return headers

    def middleware(environ, start_response):
        if environ.get('REQUEST_METHOD') == 'OPTIONS':
            headers = []
            headers = _set_headers(headers)
            start_response('200 OK', headers)
            return []

        def headers_start_response(status, headers, *args, **kwargs):
            all_headers = [key.lower() for key, val in headers]
            if 'access-control-allow-origin' not in all_headers:
                headers = _set_headers(headers)
            return start_response(status, headers, *args, **kwargs)
        return app(environ, headers_start_response)

    return middleware
