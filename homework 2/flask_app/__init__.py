"""Creates and configures the Flask application."""

from pathlib import Path

from flask import Flask
from flask_socketio import SocketIO
from dotenv import load_dotenv


socketio = SocketIO()


def create_app(*, db_path=None):
    """Build the app, optionally using a separate existing database."""
    load_dotenv()

    app = Flask(__name__)
    app.secret_key = "dev-key-change-for-production"

    from flask_app.utils.database import database

    db = database()

    if db_path is not None:
        selected_path = Path(db_path).resolve()

        if not selected_path.is_file():
            raise ValueError(
                "The selected test database does not exist."
            )

        db.db_path = str(selected_path)
        print(f"Using separate database: {selected_path}")

    print("Setting up database...")
    db.createTables(purge=False)

    app.db = db
    print("Database ready.")

    socketio.init_app(app)

    with app.app_context():
        from flask_app import routes
        from flask_app.utils import socket_events

    @app.after_request
    def disable_cache(response):
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app, socketio