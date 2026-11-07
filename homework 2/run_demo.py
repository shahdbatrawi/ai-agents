"""Run the browser demo using a separate development database."""

import sqlite3
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from flask_app import create_app


def main():
    source_path = ROOT / "tests" / "calibration.db"
    demo_path = ROOT / "tests" / "demo.db"

    if not source_path.is_file():
        raise SystemExit(
            "Run python tests/calibrate_search.py first."
        )

    # Copy test data only on the first demo run.
    # Later restarts preserve additions and approved deletions.
    if not demo_path.exists():
        with closing(sqlite3.connect(source_path)) as source:
            with closing(sqlite3.connect(demo_path)) as destination:
                source.backup(destination)

        print("Created a separate demo database.")

    app, socketio = create_app(db_path=demo_path)

    print("DEVELOPMENT TEST DATA — browser demo")
    print("Open http://localhost:8080")
    print("Demo changes persist in tests/demo.db.")

    socketio.run(
        app,
        host="127.0.0.1",
        port=8080,
        debug=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()