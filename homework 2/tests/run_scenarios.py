"""
run_scenarios.py — ONE command that runs scenarios S1-S11 and prints PASS / FAIL.

    python tests/run_scenarios.py          (run it from the "homework 2" folder)

It never touches your own resume: it builds a separate test database
(tests/.test_resume.db) from the course test data in fixtures/ (or, if that folder
is missing, from tests/test_data/), and puts it back to the same starting state
before every scenario.

Scenarios marked [API] call the real OpenRouter models (chat + embeddings) and
need OPENROUTER_API_KEY / EMBEDDING_MODEL in your .env. Without a key they are
printed as SKIP. Scenarios marked [offline] need no key.
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Point the app at the TEST database and TEST data BEFORE anything from flask_app is imported.
TEST_DB = os.path.join("tests", ".test_resume.db")
BASELINE = TEST_DB + ".baseline"
FIXTURES = os.path.join(ROOT, "fixtures")
SEED_DIR = FIXTURES if os.path.exists(os.path.join(FIXTURES, "institutions.csv")) \
    else os.path.join(ROOT, "tests", "test_data")
for path in (TEST_DB, BASELINE):
    if os.path.exists(path):
        os.remove(path)
os.environ["RESUME_DB_PATH"] = TEST_DB
os.environ["RESUME_SEED_DIR"] = SEED_DIR

from flask_app.utils import trace                                   # noqa: E402
from flask_app.utils.database import database, ApprovalRequired    # noqa: E402
from flask_app.utils.chat_flow import ChatSession                   # noqa: E402
from flask_app.utils.llm import parse_plan                          # noqa: E402
from flask_app.utils.write_ops import parse_operation               # noqa: E402
from flask_app.utils.semantic_search import search_by_meaning       # noqa: E402

KEY = os.getenv("OPENROUTER_API_KEY", "")
HAS_KEY = bool(KEY) and KEY != "paste-your-key-here"


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def reset():
    shutil.copy(BASELINE, TEST_DB)
    return database()


def skills(db):
    return sorted(r["name"] for r in db.query("SELECT name FROM skills"))


def count(db, table):
    return db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


def chat(session, text):
    """Send one message; return (reply, the trace lines of that message)."""
    trace.CAPTURE = []
    reply = session.handle(text)
    lines, trace.CAPTURE = trace.CAPTURE, None
    return reply, lines


def has(lines, text):
    return any(text in line for line in lines)


def search_hits(lines):
    """The ranked search results shown in the trace, best first."""
    return [line.split("score", 1)[1] for line in lines if " score " in line]


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def show_db(label, db):
    print(f"      {label}: skills = {skills(db)}")


# ----------------------------------------------------------------------------
# scenarios (each raises AssertionError with a reason when it fails)
# ----------------------------------------------------------------------------

def s1():
    db = reset()
    reply, lines = chat(ChatSession(db), "Find my MSU experience")
    hits = search_hits(lines)
    need(hits, "no search results in the trace (search by meaning was not used)")
    need(any("Michigan State University" in h for h in hits[:3]),
         f"Michigan State University is not in the top results: {hits[:3]}")
    print(f"      top results: {[h.strip()[:60] for h in hits[:3]]}")


def s2():
    db = reset()
    reply, lines = chat(ChatSession(db), "What AI skills do I have?")
    hits = search_hits(lines)
    need(hits, "no search results in the trace")
    ml = next((i for i, h in enumerate(hits) if "Machine Learning" in h), None)
    ps = next((i for i, h in enumerate(hits) if "Public Speaking" in h), None)
    need(ml is not None, f"Machine Learning did not come back: {hits}")
    need(ps is None or ps > ml, "Public Speaking ranks above Machine Learning")
    print(f"      Machine Learning rank {ml + 1}; Public Speaking "
          f"{'not returned' if ps is None else 'rank ' + str(ps + 1)}")


def s3():
    db = reset()
    reply, lines = chat(ChatSession(db), "How many positions do I have?")
    need(has(lines, "Database Read Expert |"), "the Database Read Expert did not run")
    need(not has(lines, "Semantic Search Expert |"), "search by meaning was used for an exact question")
    reason = next(l for l in lines if "Database Read Expert |" in l)
    need("reason: -" not in reason, "the trace gives no reason")
    print(f"      {reason.strip()}")


def s4():
    db = reset()
    reply, lines = chat(ChatSession(db), "What did I do at MSU?")
    need(has(lines, "step 1/2: Semantic Search Expert"), "step 1 is not the search")
    need(has(lines, "step 2/2: Database Read Expert"), "step 2 is not the Read Expert")
    sql = next((l for l in lines if "Database Read Expert generated" in l), "")
    need("Michigan State University" in sql, f"step 2 did not use the exact name: {sql[-120:]}")


def s5():
    db = reset()
    experience = db.query("SELECT name FROM experiences ORDER BY experience_id LIMIT 1")[0]["name"]
    chat(ChatSession(db), f"Add the skill Kubernetes at level 6 to my {experience} experience")
    need("Kubernetes" in skills(db), "the skill was not added")
    print("      ... restarting the app (new database object + createTables) ...")
    restarted = database()
    restarted.createTables()
    need("Kubernetes" in skills(restarted), "the skill is gone after the restart")
    row = restarted.query("SELECT COUNT(*) AS n FROM embeddings e JOIN skills s "
                          "ON e.source_table='skills' AND e.source_id=s.skill_id WHERE s.name='Kubernetes'")
    need(row[0]["n"] == 1, "the skill has no embedding after the restart")
    found = search_by_meaning(restarted, "container orchestration", tables=["skills"], top_k=1, min_score=0.0)
    need(found and found[0]["name"] == "Kubernetes", f"search by meaning did not find it: {found}")


def _delete_request(db):
    session = ChatSession(db)
    before = skills(db)
    reply, _ = chat(session, "Remove the Public Speaking skill")
    need(session.pending is not None, "nothing is waiting for approval")
    need("Public Speaking" in reply, f"the reply does not show the exact action: {reply}")
    need(skills(db) == before, "the database changed before approval")
    return session, before, reply


def s6():
    db = reset()
    session, before, reply = _delete_request(db)
    show_db("before", db)
    reply, _ = chat(session, "no")
    show_db("after no", db)
    need(skills(db) == before, "the database changed after 'no'")
    need("Cancelled" in reply, f"unexpected reply: {reply}")


def s7():
    db = reset()
    session, before, _ = _delete_request(db)
    show_db("before", db)
    chat(session, "yes")
    show_db("after yes", db)
    expected = list(before)
    expected.remove("Public Speaking")
    need(skills(db) == sorted(expected), "more or less than the shown action was deleted")


def s8():
    db = reset()
    session, before, _ = _delete_request(db)
    reply, _ = chat(session, "maybe")
    need(skills(db) == before and session.pending is None, "'maybe' did something or left the action pending")
    session, before, _ = _delete_request(db)
    chat(session, "What is this page about?")
    need(skills(db) == before and session.pending is None, "changing the subject did not cancel the action")
    chat(session, "yes")
    need(skills(db) == before, "a later 'yes' approved the old action")


def s9():
    db = reset()
    session = ChatSession(db)
    before = skills(db)
    reply, _ = chat(session, "Clean up my skills so the list is empty")
    show_db("before", db)
    need(session.pending is not None, "the request was not paused for approval")
    need(skills(db) == before, "skills were deleted without approval")
    chat(session, "no")
    show_db("after no", db)
    need(skills(db) == before, "skills changed after 'no'")


def s10():
    db = reset()
    embeddings_before = count(db, "embeddings")
    good_model = os.environ.get("EMBEDDING_MODEL")
    os.environ["EMBEDDING_MODEL"] = "not-a-real-model/for-testing"   # only for this test
    try:
        session = ChatSession(db)
        reply, lines = chat(session, "Find my MSU experience")
    finally:
        if good_model is None:
            os.environ.pop("EMBEDDING_MODEL", None)
        else:
            os.environ["EMBEDDING_MODEL"] = good_model
    need(has(lines, "embedding failed") or has(lines, "SEARCH FAILED"), "the failure is not in the trace")
    need(not search_hits(lines), "search returned matches even though embedding failed")
    need(count(db, "embeddings") == embeddings_before, "an embedding was stored by the failed call")
    need("Michigan State University" not in reply, f"the reply presents a record anyway: {reply}")
    print(f"      reply while failing: {reply[:100]}")
    reply, lines = chat(session, "How many skills do I have?")
    need(not has(lines, "error:"), "the app broke after the failure")


def s11():
    db = reset()
    before = {t: count(db, t) for t in ("institutions", "positions", "experiences", "skills")}
    reply, lines = chat(ChatSession(db), "Find my Harvard experience")
    need(has(lines, "NO MATCH"), "the search did not report NO MATCH")
    need({t: count(db, t) for t in before} == before, "a record was created")
    print(f"      reply: {reply[:100]}")


def u1():
    for bad in ('import os; os.system("x")', '{"operation": "drop_table"}',
                '{"operation": "add_skill", "skill": "X", "experience": "A", "skill_level": 99}',
                "__import__('os').system('x')"):
        try:
            parse_operation(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted a forbidden operation: {bad}")
    for bad in ('[{"expert": "Hacker", "message": "x"}]', "eval('1+1')", "[]"):
        try:
            parse_plan(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted a bad plan: {bad}")


def u2():
    db = reset()
    before = skills(db)
    delete_all = {"operation": "delete_all_skills"}
    for approved in (None, {"operation": "delete_skill", "skill": "Python"}):
        try:
            db.apply_operation(delete_all, approved_operation=approved)
        except ApprovalRequired:
            continue
        raise AssertionError("a destructive operation ran without its own approval")
    need(skills(db) == before, "skills changed without approval")


SCENARIOS = [
    ("U1", "forbidden operations / plans are refused", False, u1),
    ("U2", "the write code itself refuses an unapproved delete", False, u2),
    ("S1", "abbreviation found by meaning", True, s1),
    ("S2", "AI skills found, unrelated skill not", True, s2),
    ("S3", "exact question goes to the Read Expert", True, s3),
    ("S4", "two dependent steps (resolve name, then look up)", True, s4),
    ("S5", "added skill survives a restart and is searchable", True, s5),
    ("S6", "deletion then 'no' leaves the database unchanged", True, s6),
    ("S7", "deletion then 'yes' runs only the shown action", True, s7),
    ("S8", "'maybe' / change of subject approve nothing", True, s8),
    ("S9", "'clean up my skills' is paused (no danger word)", True, s9),
    ("S10", "embedding failure: clear error, no fake match", True, s10),
    ("S11", "Harvard (not in the data): not found, nothing invented", True, s11),
]


def main():
    print(f"Test data: {SEED_DIR}")
    print(f"Test database: {TEST_DB} (your own resume.db is not touched)\n")
    if HAS_KEY:
        database().createTables()          # builds the test DB and its embeddings
        shutil.copy(TEST_DB, BASELINE)
    else:
        print("No OPENROUTER_API_KEY found: [API] scenarios will be skipped.\n")
        database().createTables()
        shutil.copy(TEST_DB, BASELINE)

    outcome = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for sid, title, needs_api, run in SCENARIOS:
        label = f"{sid:<4} {'[API]' if needs_api else '[offline]'} {title}"
        if needs_api and not HAS_KEY:
            print(f"SKIP {label}")
            outcome["SKIP"] += 1
            continue
        print(f"---- {label}")
        try:
            run()
            print(f"PASS {sid}")
            outcome["PASS"] += 1
        except AssertionError as error:
            print(f"FAIL {sid}: {error}")
            outcome["FAIL"] += 1
        except Exception as error:   # a crash is a FAIL, not a stop
            print(f"FAIL {sid}: crashed with {type(error).__name__}: {error}")
            outcome["FAIL"] += 1

    print(f"\n==== {outcome['PASS']} passed, {outcome['FAIL']} failed, {outcome['SKIP']} skipped")
    sys.exit(1 if outcome["FAIL"] else 0)


if __name__ == "__main__":
    main()