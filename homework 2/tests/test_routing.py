"""Real API integration checks using development sample data."""

import json
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from flask_app.utils.database import database
from flask_app.utils.llm import handle_ai_chat_request


test_database = ROOT / "tests" / "calibration.db"

if not test_database.exists():
    raise SystemExit("Run tests/calibrate_search.py first.")

db = database()
db.db_path = str(test_database)

# Preserve the test records and reload the latest expert prompts.
db.createTables()


def run_case(label, message, check):
    events = []
    request_id = uuid4().hex[:12]

    def trace(event, **details):
        record = {
            "request_id": request_id,
            "event": event,
            **details,
        }
        events.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    print(f"\n{label}: {message}", flush=True)

    try:
        reply = handle_ai_chat_request(
            db,
            role="Orchestrator",
            message=message,
            trace=trace,
        )

        print("REPLY:", reply, flush=True)
        check(events, reply)
        print(f"{label}: PASS", flush=True)
        return True

    except Exception as error:
        print(
            f"{label}: FAIL — {type(error).__name__}: {error}",
            flush=True,
        )
        return False


def accepted_matches(events):
    searches = [
        event for event in events
        if event["event"] == "semantic_search"
    ]
    assert searches, "Semantic search did not run."

    return [
        match
        for event in searches
        for match in event["ranked_results"]
        if match["score"] >= event["cutoff"]
    ]


def check_msu(events, reply):
    matches = accepted_matches(events)
    assert any(
        match["table"] == "institutions"
        and "Michigan State University" in match["text"]
        for match in matches
    ), "MSU was not resolved."


def check_ai_skills(events, reply):
    matches = accepted_matches(events)
    assert matches, "No relevant skills were found."
    assert all(match["table"] == "skills" for match in matches)
    assert any("Machine Learning" in match["text"] for match in matches)
    assert not any("Public Speaking" in match["text"] for match in matches)


def check_exact_read(events, reply):
    routes = [
        event for event in events
        if event["event"] == "route"
    ]
    assert routes
    assert routes[0]["experts"] == ["Database Read Expert"]
    assert any(event["event"] == "read" for event in events)
    assert not any(
        event["event"] == "semantic_search" for event in events
    )


def check_dependent(events, reply):
    check_msu(events, reply)

    searches = [
        index for index, event in enumerate(events)
        if event["event"] == "semantic_search"
    ]
    reads = [
        (index, event)
        for index, event in enumerate(events)
        if event["event"] == "dependent_read"
    ]

    assert reads, "Dependent lookup did not run."
    index, read = reads[0]

    assert index > searches[0]
    assert read["resolved_institution"]["name"] == (
        "Michigan State University"
    )
    assert read["row_count"] > 0
    assert read["source_match"]["record_id"] == (
        read["resolved_institution"]["inst_id"]
    )


def check_harvard(events, reply):
    assert not accepted_matches(events)
    assert reply == "No matching records found."
    assert not any(
        event["event"] == "dependent_read" for event in events
    )


cases = [
    ("D1", "Find my MSU experience", check_msu),
    ("D2", "What AI skills do I have?", check_ai_skills),
    ("D3", "List all my skills", check_exact_read),
    ("D4", "What did I do at MSU?", check_dependent),
    ("D5", "Find my Harvard experience", check_harvard),
]

results = [
    run_case(label, message, check)
    for label, message, check in cases
]

print(f"\nDevelopment checks: {sum(results)}/{len(results)} PASS")
raise SystemExit(0 if all(results) else 1)
