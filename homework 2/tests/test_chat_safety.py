"""Chat approval integration checks on a temporary test database."""

import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from flask_app import socketio
from flask_app.utils.database import database


source_db = ROOT / "tests" / "calibration.db"

if not source_db.exists():
    raise SystemExit("Run tests/calibrate_search.py first.")


with tempfile.TemporaryDirectory() as temporary:
    test_db = Path(temporary) / "chat_test.db"

    with closing(sqlite3.connect(source_db)) as source:
        with closing(sqlite3.connect(test_db)) as destination:
            source.backup(destination)

    db = database()
    db.db_path = str(test_db)
    db.createTables()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "temporary-test-key"
    app.config["TESTING"] = True
    app.db = db

    socketio.init_app(app, async_mode="threading")

    # Register the same event handlers used by the browser chat.
    from flask_app.utils import socket_events

    client = socketio.test_client(app)

    def send(message):
        print(f"\nUSER: {message}", flush=True)
        client.emit("send_message", {"message": message})

        replies = [
            event["args"][0]["response"]
            for event in client.get_received()
            if event["name"] == "receive_message"
        ]

        assert replies, "Chat returned no reply."
        reply = replies[-1]
        print("CHAT:", reply, flush=True)
        return reply

    def skills():
        return db.query("SELECT * FROM skills ORDER BY skill_id")

    def other_resume_data():
        return {
            table: db.query(f"SELECT * FROM {table}")
            for table in ("institutions", "positions", "experiences")
        }

    original_skills = skills()
    original_other = other_resume_data()

    targets = db.query(
        """
        SELECT s.*
        FROM skills AS s
        JOIN experiences AS e
            ON e.experience_id = s.experience_id
        WHERE s.name = ? AND e.name = ?
        """,
        ("Python", "CSE 847"),
    )

    assert len(targets) == 1, "Expected exactly one test Python skill."
    target = targets[0]

    def request_deletion():
        before = skills()
        reply = send("Remove Python from CSE 847")

        assert "Python" in reply
        assert "CSE 847" in reply
        assert "yes" in reply.lower()
        assert skills() == before, "Deletion ran before approval."

    try:
        # S6 behavior: no preserves every resume record.
        request_deletion()
        reply = send("no")

        assert "cancelled" in reply.lower()
        assert skills() == original_skills
        assert other_resume_data() == original_other
        print("S6 DEVELOPMENT: PASS", flush=True)

        # S7 behavior: yes deletes exactly the displayed record.
        request_deletion()
        reply = send("yes")

        expected = [
            row for row in original_skills
            if row["skill_id"] != target["skill_id"]
        ]

        assert skills() == expected
        assert other_resume_data() == original_other
        print("S7 DEVELOPMENT: PASS", flush=True)

        # Restore this record only in the temporary test database.
        db.query(
            "INSERT INTO skills "
            "(skill_id, experience_id, name, skill_level) "
            "VALUES (?, ?, ?, ?)",
            (
                target["skill_id"],
                target["experience_id"],
                target["name"],
                target["skill_level"],
            ),
        )

        # S8 behavior: maybe cancels; later yes cannot approve.
        request_deletion()
        send("maybe")
        reply = send("yes")

        assert "no pending action" in reply.lower()
        assert skills() == original_skills

        # Changing the subject also invalidates old approval.
        request_deletion()
        reply = send("List all my skills")

        assert "previous pending action cancelled" in reply.lower()
        assert "Python" in reply

        reply = send("yes")
        assert "no pending action" in reply.lower()
        assert skills() == original_skills
        print("S8 DEVELOPMENT: PASS", flush=True)

        # S9 behavior: indirect wording must still pause.
        reply = send("Clean up my skills so the list is empty")

        assert "yes" in reply.lower()
        assert "delete" in reply.lower()
        assert skills() == original_skills

        send("no")
        assert skills() == original_skills
        assert other_resume_data() == original_other
        print("S9 DEVELOPMENT: PASS", flush=True)

    finally:
        client.disconnect()

print("\nChat safety checks finished; app resume.db was not changed.")
