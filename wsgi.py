"""WSGI entry point for Render.com deployment."""
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response as WerkzeugResponse
from app import app as flask_app

# Mount Flask at /tools/journal-club so that:
#   - Incoming PATH_INFO /tools/journal-club/journals → Flask sees /journals
#   - url_for('journals') generates /tools/journal-club/journals (SCRIPT_NAME prepended)
#   - Redirects and links work correctly through the Vercel proxy
app = DispatcherMiddleware(
    WerkzeugResponse('Not Found', status=404),
    {'/tools/journal-club': flask_app},
)

if __name__ == "__main__":
    flask_app.run()
