"""WSGI entry point for Render.com deployment."""
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from app import app as flask_app


def _health_ok(environ, start_response):
    """Fallback WSGI app: returns 200 for / (Render health check), 404 otherwise."""
    path = environ.get('PATH_INFO', '/')
    if path in ('/', '/health'):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'ok']
    start_response('404 Not Found', [('Content-Type', 'text/plain')])
    return [b'Not Found']


# Mount Flask at /tools/journal-club so that:
#   - Render health check hits / -> _health_ok -> 200
#   - User requests /tools/journal-club/... -> Flask sees /...
#   - url_for() generates /tools/journal-club/... via SCRIPT_NAME
app = DispatcherMiddleware(_health_ok, {'/tools/journal-club': flask_app})

if __name__ == "__main__":
    flask_app.run()
