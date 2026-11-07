"""
Creates and configures the Flask application.
"""

from flask import Flask
from flask_socketio import SocketIO
from dotenv import load_dotenv

socketio = SocketIO()


def create_app():
    """Build and return the Flask application and Socket.IO instance."""
    load_dotenv()

    app = Flask(__name__)
    app.secret_key = 'dev-key-change-for-production'

    from flask_app.utils.database import database

    db = database()
    print("Setting up database...")

    # Keep existing tables and data across restarts.
    db.createTables(purge=False)

    app.db = db
    print("Database ready.")

    socketio.init_app(app)

    with app.app_context():
        from flask_app import routes
        from flask_app.utils import socket_events

    @app.after_request
    def disable_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app, socketio