"""Development checks for persistent chat additions and API failure."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

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
    test_db = Path(temporary) / "embedding_writes.db"

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

    try:
        # S5: Add through the real chat handler with exact quoted names.
        send(
            'Add a skill named "Rust programming" '
            'to the experience named "BRAINWORKS" '
            'with skill level 7. Preserve the exact quoted names.'
        )

        rows = db.query(
            """
            SELECT s.*
            FROM skills AS s
            JOIN experiences AS e
                ON e.experience_id = s.experience_id
            WHERE s.name = ? AND e.name = ?
            """,
            ("Rust programming", "BRAINWORKS"),
        )

        assert len(rows) == 1, (
            "The skill was not added with the exact requested name "
            "and experience."
        )
        assert rows[0]["skill_level"] == 7

        skill_id = rows[0]["skill_id"]

        saved = db.query(
            "SELECT * FROM embeddings "
            "WHERE source_table = 'skills' "
            "AND record_id = ? AND model = ?",
            (
                skill_id,
                os.environ["OPENROUTER_EMBEDDING_MODEL"],
            ),
        )

        assert len(saved) == 1, (
            "Embedding was not saved with the skill."
        )

        print(
            "PASS: Chat saved the exact skill and its embedding.",
            flush=True,
        )

        client.disconnect()

        # Start a separate Python process to check persistence.
        restart_check = """
import json
import os
import sys

from flask_app.utils.database import database
from flask_app.utils.semantic_search import SemanticSearch, validate_vector

db = database()
db.db_path = sys.argv[1]
skill_id = int(sys.argv[2])
db.createTables()

rows = db.query(
    "SELECT * FROM skills WHERE skill_id = ?",
    (skill_id,),
)
assert len(rows) == 1
assert rows[0]["name"] == "Rust programming"
assert rows[0]["skill_level"] == 7

search = SemanticSearch(db)

saved = db.query(
    "SELECT * FROM embeddings "
    "WHERE source_table = 'skills' AND record_id = ? AND model = ?",
    (skill_id, search.model),
)
assert len(saved) == 1, "Embedding missing before search."
validate_vector(json.loads(saved[0]["vector_json"]))

matches = search.search(
    "Rust",
    ["skills"],
    min_score=float(os.environ["SEMANTIC_MIN_SCORE"]),
)
print("RESTART SEARCH:", json.dumps(matches), flush=True)

assert any(
    match["record_id"] == skill_id
    for match in matches
), "Semantic search did not find the saved skill."

print("S5 DEVELOPMENT: PASS", flush=True)
"""

        subprocess.run(
            [
                sys.executable,
                "-c",
                restart_check,
                str(test_db),
                str(skill_id),
            ],
            cwd=ROOT,
            check=True,
        )

        client = socketio.test_client(app)

        # S10: Change the model only inside this test request.
        before_skills = db.query(
            "SELECT * FROM skills ORDER BY skill_id"
        )
        before_embeddings = db.query(
            "SELECT * FROM embeddings "
            "ORDER BY source_table, record_id, model"
        )

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_EMBEDDING_MODEL":
                    "invalid-model-for-hw2-failure-test"
            },
        ):
            reply = send(
                'Add a skill named "Temporary Failure Skill" '
                'to the experience named "BRAINWORKS" '
                'with skill level 5. Preserve the exact quoted names.'
            )

        assert "embedding request failed" in reply.lower(), (
            "Expected a clear embedding API failure."
        )

        assert db.query(
            "SELECT * FROM skills ORDER BY skill_id"
        ) == before_skills, (
            "A skill was saved after embedding failure."
        )

        assert db.query(
            "SELECT * FROM embeddings "
            "ORDER BY source_table, record_id, model"
        ) == before_embeddings, (
            "Invalid embedding data was saved."
        )

        # The original environment has been restored automatically.
        reply = send("List all my skills")

        assert "Rust programming" in reply
        assert "Temporary Failure Skill" not in reply

        print(
            "S10 DEVELOPMENT: PASS — clear failure, "
            "no saved data, chat still works.",
            flush=True,
        )

    finally:
        if client.is_connected():
            client.disconnect()

print(
    "\nFinished; app resume.db and the real API key were not changed."
)