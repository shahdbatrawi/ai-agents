

"""
llm.py — sends messages to an AI language model via the OpenRouter API.

This file is the bridge between your Flask app and an AI model (GPT-3.5).
When a student types a message in the chat, it travels here, gets sent to
OpenRouter, and the AI's reply comes back.

KEY CONCEPTS:
  - API (Application Programming Interface): a way for two programs to talk
    to each other over the internet. OpenRouter exposes an API we can call.
  - HTTP POST request: sending data to a server (like submitting a form).
    We POST the conversation to OpenRouter and it POSTs back the AI reply.
  - System prompt: instructions given to the AI before the conversation starts.
    Think of it as the AI's job description.

SAFETY MODEL FOR WRITES:
  The Database Write Expert only *proposes* an action as JSON. Code in this
  file validates it, resolves any lookups into plain values, checks for
  duplicates / missing rows, shows the user the exact action, and only runs
  it after an explicit "yes". No SQL coming from the model is ever executed
  as part of a write.
"""

import os
import re
import json
import time
import uuid
import threading
import traceback

import requests
from jinja2 import Template
from dotenv import load_dotenv
from flask import session as flask_session, has_request_context
from flask_app.utils.semantic_search import semantic_search_expert
from flask_app.utils.embeddings import create_and_store_embeddings

load_dotenv()  # Load environment variables from .env file

# The URL we send our messages to.
# OpenRouter acts as a single gateway to many different AI models.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Which AI model to use. OpenRouter supports many models.
# Models with ':free' suffix are free to use — no API credits needed.
# See all available models at: https://openrouter.ai/models
DEFAULT_MODEL = os.getenv(
    "DEFAULT_MODEL", "openai/gpt-4o-mini"
)  # fallback if .env is missing


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# One shared template for every expert's system prompt. Each expert just
# fills in different values for role/domain/instructions/context/examples.
#
# We use Jinja2 here (not manual string replacement) because it's already a
# Flask dependency — it's the exact same {{ }} / {% if %} syntax you've been
# reading in resume.html, just rendering a prompt string instead of a page.
MASTER_TEMPLATE = Template(
    """\
You are a {{ role }}, an expert in {{ domain }}.

{{ specific_instructions }}
{% if background_context %}
Context:
{{ background_context }}
{% endif %}
{% if few_shot_examples %}
Examples:
{{ few_shot_examples }}
{% endif %}
Request: {{ request }}
""",
    trim_blocks=True,
    lstrip_blocks=True,
)


def fill_template(
    role,
    domain,
    specific_instructions,
    request,
    background_context="",
    few_shot_examples="",
):
    """
    Render MASTER_TEMPLATE into one expert's full system prompt.

    background_context and few_shot_examples are optional: the {% if %}
    blocks above drop the whole section — header included — when the
    argument is empty, instead of leaving a dangling "Context:" with
    nothing underneath it.
    """
    return MASTER_TEMPLATE.render(
        role=role,
        domain=domain,
        specific_instructions=specific_instructions,
        background_context=background_context,
        few_shot_examples=few_shot_examples,
        request=request,
    ).strip()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEMANTIC_ROLE = "Semantic Search Expert"

# Roles the Orchestrator is allowed to call. "Orchestrator" is deliberately
# NOT here: a plan step that calls the Orchestrator would call itself.
PLAN_ROLES = {
    "Database Read Expert",
    "Database Write Expert",
    "Content Expert",
    SEMANTIC_ROLE,
}
MAX_PLAN_STEPS = 6

CONFIRM_WORDS = {"yes", "y", "confirm"}
PENDING_TTL_SECONDS = 600  # an unanswered confirmation expires after 10 minutes
MAX_VALUE_LENGTH = 2000

ALLOWED_WRITE_ACTIONS = {"insert", "delete"}

ALLOWED_WRITE_TABLES = {
    "institutions",
    "positions",
    "experiences",
    "skills",
}

ALLOWED_COLUMNS = {
    "institutions": {
        "inst_id",
        "type",
        "name",
        "department",
        "address",
        "city",
        "state",
        "zip",
    },
    "positions": {
        "position_id",
        "inst_id",
        "title",
        "responsibilities",
        "start_date",
        "end_date",
    },
    "experiences": {
        "experience_id",
        "position_id",
        "name",
        "description",
        "hyperlink",
        "start_date",
        "end_date",
    },
    "skills": {"skill_id", "experience_id", "name", "skill_level"},
}

PRIMARY_KEYS = {
    "institutions": "inst_id",
    "positions": "position_id",
    "experiences": "experience_id",
    "skills": "skill_id",
}

# column -> (table it points to, id column there, display column, friendly label)
FK_REFERENCES = {
    "inst_id": ("institutions", "inst_id", "name", "institution"),
    "position_id": ("positions", "position_id", "title", "position"),
    "experience_id": ("experiences", "experience_id", "name", "experience"),
}

# What makes two rows "the same entry" when inserting (duplicate check).
MAIN_COLUMN = {
    "institutions": "name",
    "positions": "title",
    "experiences": "name",
    "skills": "name",
}
DUPLICATE_KEYS = {
    "institutions": ["name", "department"],
    "positions": ["inst_id", "title"],
    "experiences": ["position_id", "name"],
    "skills": ["experience_id", "name"],
}


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def _short(value, limit=160):
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def trace(request_id, event, **fields):
    """
    One greppable line per decision:
      [trace 3fa91c2e] route role='Database Write Expert' reason='...' approval='pending'
    Every line of one user message shares the same request_id.
    """
    extras = " ".join(f"{key}={_short(val)!r}" for key, val in fields.items())
    print(f"[trace {request_id}] {event} {extras}".rstrip(), flush=True)


# ---------------------------------------------------------------------------
# Per-session pending confirmations (replaces the old global variable)
# ---------------------------------------------------------------------------

_PENDING = {}  # session id -> pending action dict
_PENDING_LOCK = threading.Lock()


def get_session_id(session_id=None):
    """
    Identify the chat session. Callers may pass their own id; otherwise we
    use a random id stored in the Flask session cookie. Outside a request
    (tests, scripts) everything shares the id "default".
    """
    if session_id:
        return str(session_id)
    try:
        if has_request_context():
            sid = flask_session.get("chat_sid")
            if not sid:
                sid = uuid.uuid4().hex
                flask_session["chat_sid"] = sid
            return sid
    except Exception as error:  # e.g. SECRET_KEY not configured
        print(f"Could not use Flask session for chat id: {error}")
    return "default"


def set_pending(sid, pending):
    pending["created"] = time.time()
    with _PENDING_LOCK:
        _PENDING[sid] = pending


def get_pending(sid):
    with _PENDING_LOCK:
        pending = _PENDING.get(sid)
        if pending and time.time() - pending["created"] > PENDING_TTL_SECONDS:
            del _PENDING[sid]
            return None
        return pending


def pop_pending(sid):
    with _PENDING_LOCK:
        pending = _PENDING.pop(sid, None)
    if pending and time.time() - pending["created"] > PENDING_TTL_SECONDS:
        return None
    return pending


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def handle_ai_chat_request(db, role, message, session_id=None):
    """
    Route a chat message to the named expert. role=None keeps Homework 0's
    original single-prompt behavior as a fallback, so nothing about the
    basic chat flow breaks while you're building this out.

    session_id is optional; if omitted it comes from the Flask session.
    """
    request_id = uuid.uuid4().hex[:8]
    sid = get_session_id(session_id)
    trace(request_id, "request", role=role, session=sid[:8], message=message)

    try:
        

        # A write is waiting for yes/no: this message is the answer, whatever
        # role the UI sent it with. (Only top-level messages get here --
        # orchestrator sub-steps never touch the pending action.)
        if get_pending(sid) is not None:
            trace(
                request_id,
                "route",
                role="confirmation",
                reason="a write action is awaiting approval in this session",
            )
            return confirm_pending_write_action(db, message, sid, request_id)
        if role is None:
                    trace(request_id, "route", role=None, reason="no role selected, plain chat")
                    return send_message(message)

        if role == "Orchestrator":
            trace(request_id, "route", role=role, reason="role selected by caller")
            ok, plan_text = generate_expert_output(db, role, message)
            if not ok:
                return plan_text
            print(f"[Orchestrator] generated:\n{plan_text}\n")
            return run_orchestrator_plan(db, message, plan_text, sid, request_id)

        text, _ = run_expert(
            db, role, message, sid, request_id, reason="role selected by caller"
        )
        return text

    except Exception as error:
        print(f"[trace {request_id}] unhandled error: {error!r}")
        traceback.print_exc()
        return "Sorry, something went wrong while handling that request. Please try again."


def generate_expert_output(db, role, message, extra_context=""):
    """
    Build the expert's system prompt and ask the model. Returns (ok, text).
    extra_context goes into the prompt's Context section -- it is never
    glued onto the user's message.
    """
    config = db.getLLMRoles().get(role)
    if config is None:
        return False, f"Sorry, I don't have an expert called '{role}'."

    background_context = config["background_context"] or ""
    if role == "Content Expert":
        # No page-scraping in this stack -- "current page content" is the
        # resume data itself, fetched fresh on every request.
        background_context += "\n" + db.getResumeText()
    if extra_context:
        background_context += "\n" + extra_context

    system_prompt = fill_template(
        role=config["role"],
        domain=config["domain"],
        specific_instructions=config["specific_instructions"],
        background_context=background_context,
        few_shot_examples=config["few_shot_examples"] or "",
        request=message,
    )
    ok, output = call_llm(message, system_prompt)
    return ok, output.strip() if ok else output


def run_expert(db, role, message, sid, request_id, reason, extra_context=""):
    """
    Run ONE expert (not the Orchestrator). Returns (text, awaiting_confirmation).
    """
    trace(request_id, "route", role=role, reason=reason)

    # The semantic search needs no LLM call: it embeds the raw message itself.
    if role == SEMANTIC_ROLE:
        try:
            result = semantic_search_expert(db, message)
        except Exception as error:
            print(f"Semantic search failed: {error!r}")
            return "Sorry, the search couldn't be completed.", False
        trace(request_id, "result", role=role, approval="not_required")
        return result, False

    ok, output = generate_expert_output(db, role, message, extra_context)
    if not ok:
        trace(request_id, "result", role=role, approval="not_required", error=output)
        return output, False

    print(f"[{role}] generated:\n{output}\n")  # the rubric checks this output

    if role == "Database Read Expert":
        trace(request_id, "result", role=role, approval="not_required")
        return execute_read_query(db, output), False

    if role == "Database Write Expert":
        reply = execute_write_action(db, output, sid, request_id)
        pending = get_pending(sid)
        awaiting = pending is not None and pending.get("request_id") == request_id
        trace(
            request_id,
            "result",
            role=role,
            approval="pending" if awaiting else "not_needed_or_rejected",
        )
        return reply, awaiting

    if role == "Content Expert":
        trace(request_id, "result", role=role, approval="not_required")
        return output, False  # output is already the final answer

    return f"Sorry, I don't know how to run '{role}'.", False


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


def execute_read_query(db, sql):
    """
    Run the Database Read Expert's generated SQL. We refuse anything that
    isn't a SELECT -- this expert is read-only by design, so there's never
    a legitimate reason to run anything else, even if a user's message
    somehow tricks the model into generating something else.
    """
    if not sql.strip().upper().startswith("SELECT"):
        return "Sorry, I couldn't safely answer that question."
    try:
        return str(db.query(sql))
    except Exception as error:
        print(f"Read Expert query failed: {error}")
        return "Sorry, that question couldn't be answered."


# ---------------------------------------------------------------------------
# Write path: helpers
# ---------------------------------------------------------------------------

_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|"
    r"vacuum|truncate|load_extension)\b",
    re.IGNORECASE,
)
SAFE_FAIL = "Sorry, I couldn't safely perform that operation."


def first_value(rows):
    """First column of the first row, whether rows are tuples, lists or dicts."""
    try:
        rows = list(rows or [])
    except TypeError:
        return None
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        values = list(row.values())
    elif hasattr(row, "keys"):  # sqlite3.Row and similar
        values = [row[key] for key in row.keys()]
    elif isinstance(row, (list, tuple)):
        values = list(row)
    else:
        return row
    return values[0] if values else None


def is_subquery(value):
    return isinstance(value, str) and re.match(r"^\s*\(\s*select\b", value, re.I)


def validate_subquery(value):
    """
    The model may reference a parent row as "(SELECT experience_id FROM
    experiences WHERE name = 'MSU Research')". We never splice that into a
    write. We only allow it if it is a single, read-only SELECT over the
    resume tables, run it ourselves, and use the plain value it returns.
    Returns the inner SELECT text, or None if it isn't acceptable.
    """
    text = value.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return None
    inner = text[1:-1].strip()
    bare = _STRING_LITERAL.sub("''", inner)  # ignore keywords inside 'quoted text'
    if ";" in bare or "--" in bare or "/*" in bare:
        return None
    if bare.count("(") != bare.count(")"):
        return None
    if _FORBIDDEN_SQL.search(bare):
        return None
    tables = re.findall(r"\b(?:from|join)\s+([A-Za-z_]\w*)", bare, re.I)
    if not tables or any(t.lower() not in ALLOWED_WRITE_TABLES for t in tables):
        return None
    return inner


def resolve_values(db, columns, values):
    """
    Turn the model's values into plain literals. Returns (values, error).
    Lookups are allowed only for *_id columns and must match exactly one row.
    """
    resolved = []
    for column, value in zip(columns, values):
        if isinstance(value, (dict, list, tuple)):
            return None, SAFE_FAIL
        if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
            return None, SAFE_FAIL

        if is_subquery(value):
            label = FK_REFERENCES.get(column, (None, None, None, column))[3]
            inner = validate_subquery(value) if column.endswith("_id") else None
            if inner is None:
                print(f"Rejected lookup for column {column}: {value}")
                return None, SAFE_FAIL
            try:
                rows = list(db.query(inner) or [])
            except Exception as error:
                print(f"Lookup failed: {error!r}")
                return None, f"Sorry, I couldn't look up the {label} you mentioned."
            if not rows:
                return None, f"I couldn't find that {label} in your resume."
            if len(rows) > 1:
                return (
                    None,
                    f"More than one {label} matches that description. "
                    "Please be more specific.",
                )
            value = first_value(rows)
            if value is None or is_subquery(value):
                return None, SAFE_FAIL

        resolved.append(value)
    return resolved, None


def build_where(columns, values):
    """
    Parameterised WHERE clause. Column names are allow-listed before this is
    called. Text columns match case-insensitively ("python" finds "Python").
    """
    clauses, params = [], []
    for column, value in zip(columns, values):
        if value is None:
            clauses.append(f"{column} IS NULL")
        elif isinstance(value, str) and not column.endswith("_id"):
            clauses.append(f"LOWER({column}) = LOWER(?)")
            params.append(value)
        else:
            clauses.append(f"{column} = ?")
            params.append(value)
    return " AND ".join(clauses), tuple(params)


def count_rows(db, table, where="", params=()):
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    rows = db.query(sql, params) if params else db.query(sql)
    return int(first_value(rows) or 0)


def lookup_label(db, column, value):
    """Human-readable name for an id, e.g. experience_id 3 -> 'MSU Research'."""
    ref = FK_REFERENCES.get(column)
    if ref is None or value is None:
        return None
    table, id_col, name_col, _ = ref
    try:
        return first_value(
            db.query(f"SELECT {name_col} FROM {table} WHERE {id_col} = ?", (value,))
        )
    except Exception:
        return None


def describe(db, columns, values):
    """'name = Python, skill_level = 5, experience = MSU Research'"""
    parts = []
    for column, value in zip(columns, values):
        ref = FK_REFERENCES.get(column)
        name = lookup_label(db, column, value) if ref else None
        if name is not None:
            parts.append(f"{ref[3]} = {name}")
        elif value is None:
            parts.append(f"{column} = (empty)")
        else:
            parts.append(f"{column} = {value}")
    return ", ".join(parts)


def is_duplicate(db, table, columns, values):
    """True if an entry with the same natural key already exists."""
    main = MAIN_COLUMN[table]
    if main not in columns:
        return False
    given = dict(zip(columns, values))
    key_cols = [c for c in DUPLICATE_KEYS[table] if c in given]
    where, params = build_where(key_cols, [given[c] for c in key_cols])
    return count_rows(db, table, where, params) > 0


# ---------------------------------------------------------------------------
# Write path: propose (needs confirmation) and execute (after "yes")
# ---------------------------------------------------------------------------


def execute_write_action(db, generated_code, sid=None, request_id=None):
    """
    Validate a Database Write Expert response and, if it is safe and makes
    sense, store it as the session's pending action and return the exact
    confirmation question. Nothing is written here.

    The expert must return JSON, not executable code:

      insert:
        {"action": "insert", "table": "skills",
         "columns": ["experience_id", "name", "skill_level"],
         "values": ["(SELECT experience_id FROM experiences WHERE name = 'MSU Research')", "Python", 5]}

      delete one/some rows (every column=value pair must match):
        {"action": "delete", "table": "skills",
         "columns": ["name"], "values": ["Python"]}

      delete ALL rows of a table (empty columns, only allowed for delete):
        {"action": "delete", "table": "skills", "columns": [], "values": []}

      nothing to do (e.g. earlier steps showed it already exists):
        {"action": "none"}
    """
    sid = get_session_id(sid)
    request_id = request_id or uuid.uuid4().hex[:8]

    try:
        text = generated_code.strip()
        text = text[text.find("{") : text.rfind("}") + 1]
        action = json.loads(text)
    except Exception:
        print("Write Expert returned invalid JSON.")
        return SAFE_FAIL

    if not isinstance(action, dict):
        return SAFE_FAIL

    write_action = action.get("action")
    if write_action == "none":
        return "No change was needed."
    if write_action not in ALLOWED_WRITE_ACTIONS:
        return "Sorry, that database operation is not allowed."

    table = action.get("table")
    if table not in ALLOWED_WRITE_TABLES:
        return "Sorry, that table cannot be modified."

    columns = action.get("columns")
    values = action.get("values")

    if write_action == "delete":
        # Empty columns means "delete every row" -- allowed, but the user is
        # told exactly how many rows will go before anything happens.
        columns = [] if columns is None else columns
        values = [] if values is None else values

    if (
        not isinstance(columns, list)
        or not isinstance(values, list)
        or len(values) != len(columns)
        or not all(isinstance(c, str) for c in columns)
        or len(set(columns)) != len(columns)
    ):
        return SAFE_FAIL
    if write_action == "insert" and not columns:
        return SAFE_FAIL
    if not set(columns).issubset(ALLOWED_COLUMNS[table]):
        return "Sorry, those columns cannot be modified."

    values, error = resolve_values(db, columns, values)
    if error:
        return error

    if write_action == "insert":
        # Parent rows must exist (the model may have invented an id).
        for column, value in zip(columns, values):
            ref = FK_REFERENCES.get(column)
            if ref and column != PRIMARY_KEYS[table] and value is not None:
                if count_rows(db, ref[0], f"{ref[1]} = ?", (value,)) == 0:
                    return f"I couldn't find that {ref[3]} in your resume."

        details = describe(db, columns, values)
        if is_duplicate(db, table, columns, values):
            return f"That entry already exists in the {table} table ({details}). Nothing was added."

        set_pending(
            sid,
            {
                "action": "insert",
                "table": table,
                "columns": columns,
                "values": values,
                "details": details,
                "request_id": request_id,
                "plan": None,
            },
        )
        return (
            f"Please confirm: reply yes to add this entry to the {table} table: "
            f"{details}. Reply anything else to cancel."
        )

    # delete
    where, params = build_where(columns, values)
    matches = count_rows(db, table, where, params)
    if matches == 0:
        return f"No matching entry was found in the {table} table, so nothing was deleted."

    noun = "entry" if matches == 1 else "entries"
    if columns:
        details = describe(db, columns, values)
        question = (
            f"Please confirm: reply yes to delete {matches} {noun} from the "
            f"{table} table where {details}. This cannot be undone. "
            "Reply anything else to cancel."
        )
    else:
        details = "all rows"
        question = (
            f"Please confirm: reply yes to delete ALL {matches} {noun} from the "
            f"{table} table. This cannot be undone. Reply anything else to cancel."
        )

    set_pending(
        sid,
        {
            "action": "delete",
            "table": table,
            "columns": columns,
            "values": values,
            "details": details,
            "request_id": request_id,
            "plan": None,
        },
    )
    return question


def confirm_pending_write_action(db, message, sid=None, request_id=None):
    """
    Execute the pending write action only after explicit user confirmation.
    If the action came from an Orchestrator plan, the rest of the plan then
    continues.
    """
    sid = get_session_id(sid)
    request_id = request_id or uuid.uuid4().hex[:8]

    pending = pop_pending(sid)
    if pending is None:
        return None

    answer = message.strip().lower().rstrip(".! ")
    if answer not in CONFIRM_WORDS:
        trace(request_id, "approval", status="cancelled", action=pending["action"])
        return "Operation cancelled."

    trace(request_id, "approval", status="confirmed", action=pending["action"],
          table=pending["table"], details=pending["details"])
    ok, outcome = perform_write(db, pending)
    trace(request_id, "executed", ok=ok, outcome=outcome)

    plan = pending.get("plan")
    if plan is None or not ok:
        return outcome

    role, step_message, _ = plan["results"][-1]
    plan["results"][-1] = (role, step_message, outcome)
    return _continue_plan(
        db, plan["request"], plan["steps"], plan["next"], plan["results"], sid, request_id
    )


def perform_write(db, pending):
    """Run a confirmed action. Returns (ok, message). Re-checks the database
    first, because it may have changed since the question was asked."""
    table, columns, values = pending["table"], pending["columns"], pending["values"]
    details = pending["details"]

    try:
        if pending["action"] == "insert":
            if is_duplicate(db, table, columns, values):
                return False, f"That entry already exists in the {table} table. Nothing was added."
            db.insertRows(table, columns, values)
            return True, f"New entry added to the {table} table ({details})."

        if pending["action"] == "delete":
            where, params = build_where(columns, values)
            before = count_rows(db, table, where, params)
            if before == 0:
                return False, f"No matching entry was found in the {table} table, so nothing was deleted."

            sql = f"DELETE FROM {table}" + (f" WHERE {where}" if where else "")
            db.query(sql, params) if params else db.query(sql)

            # Don't trust "no exception" -- count again to see what really happened.
            deleted = before - count_rows(db, table, where, params)
            if deleted <= 0:
                return False, f"Nothing was deleted from the {table} table."
            noun = "entry" if deleted == 1 else "entries"
            return True, f"Deleted {deleted} {noun} from the {table} table."

    except Exception as error:
        print(f"Confirmed write action failed: {error!r}")
        return False, "Operation was unsuccessful."

    return False, "Operation was unsuccessful."


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def parse_plan(db, plan_text):
    """
    Validate the whole plan BEFORE running anything, so a bad last step can't
    leave earlier writes half-done. Returns (steps, error_reason).
    """
    try:
        text = plan_text.strip().strip("`")
        text = text[text.find("[") : text.rfind("]") + 1]
        raw_steps = json.loads(text)
    except Exception:
        return None, "unparseable plan"

    if not isinstance(raw_steps, list) or not raw_steps:
        return None, "plan is not a non-empty list"
    if len(raw_steps) > MAX_PLAN_STEPS:
        return None, f"plan has more than {MAX_PLAN_STEPS} steps"

    try:
        known_roles = set(db.getLLMRoles())
    except Exception as error:
        return None, f"could not load roles: {error!r}"

    steps = []
    for index, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            return None, f"step {index} is not an object"
        role, message = step.get("role"), step.get("message")
        if not isinstance(role, str) or not isinstance(message, str) or not message.strip():
            return None, f"step {index} needs a text 'role' and 'message'"
        role = role.strip()
        if role not in PLAN_ROLES:
            return None, f"step {index} has unknown or disallowed role {role!r}"
        if role != SEMANTIC_ROLE and role not in known_roles:
            return None, f"step {index}: no llm_roles row for {role!r}"
        reason = step.get("reason")
        steps.append(
            {
                "role": role,
                "message": message.strip(),
                "reason": reason if isinstance(reason, str) else "",
            }
        )
    return steps, None


def run_orchestrator_plan(db, original_request, plan_text, sid=None, request_id=None):
    """
    Parse the Orchestrator's plan (a JSON list of {"role", "message"} steps),
    run each expert call in order, then make one final call to turn the raw
    results into a single clean reply for the chat UI.

    If a step needs the user's confirmation, the plan pauses there, the
    confirmation question is returned as-is (never re-worded by the model),
    and the remaining steps run after the user confirms.
    """
    sid = get_session_id(sid)
    request_id = request_id or uuid.uuid4().hex[:8]

    steps, error = parse_plan(db, plan_text)
    if error:
        print(f"Orchestrator plan rejected ({error}): {plan_text}")
        trace(request_id, "plan_rejected", reason=error)
        return "Sorry, I couldn't plan a response to that."

    trace(request_id, "plan", steps=[f"{s['role']}: {s['message']}" for s in steps])
    return _continue_plan(db, original_request, steps, 0, [], sid, request_id)


def _continue_plan(db, original_request, steps, start, results, sid, request_id):
    for index in range(start, len(steps)):
        step = steps[index]
        role, message = step["role"], step["message"]
        reason = step["reason"] or f"orchestrator plan step {index + 1}/{len(steps)}"
        print(f"[Orchestrator] executing: role={role}, message={message}")

        # Earlier results go into the expert's Context, not into the message,
        # and the search expert gets none: it embeds the message as the query.
        extra_context = ""
        if results and role != SEMANTIC_ROLE:
            previous = "\n".join(f"- {m} -> {r}" for _, m, r in results)
            extra_context = (
                f"Results of previous steps:\n{previous}\n"
                "If the previous results show this action is not needed, "
                'do nothing: return {"action": "none"} for a write.'
            )

        text, awaiting = run_expert(
            db, role, message, sid, request_id, reason, extra_context
        )
        results.append((role, message, text))

        if awaiting:
            pending = get_pending(sid)
            if index + 1 < len(steps):
                pending["plan"] = {
                    "request": original_request,
                    "steps": steps,
                    "next": index + 1,
                    "results": results,
                }
            trace(request_id, "plan_paused", step=index + 1, of=len(steps),
                  approval="pending")
            return text  # the exact action, verbatim

    return synthesize_reply(original_request, results)


def synthesize_reply(original_request, results):
    steps_summary = "\n".join(f"{r}: {resp}" for r, m, resp in results)
    synthesis_prompt = (
        f'The user asked: "{original_request}"\n\n'
        f"Here is what each expert found or did:\n{steps_summary}\n\n "
        "Write ONE short, clear reply. A Database Write Expert step's result "
        "is already the exact message to show the user (e.g. 'New entry added "
        "to the skills table.') -- if one is present, reuse it "
        "verbatim rather than rephrasing it. Otherwise, summarize the "
        "other results in plain language. Never mention SQL, Python, code, "
        "or these internal steps. "
        "Reply in plain text only. Do not use markdown, asterisks, tildes (~), "
        "backticks, headers, or bullet symbols. "
    )
    ok, reply = call_llm(original_request, synthesis_prompt)
    if not ok:  # fall back to the raw step results instead of an error blob
        return "\n".join(resp for _, _, resp in results)
    return reply


# ---------------------------------------------------------------------------
# Talking to OpenRouter
# ---------------------------------------------------------------------------


def call_llm(user_message, system_prompt="You are a helpful assistant."):
    """
    Send a message to the AI. Returns (ok, text): on success text is the
    reply; on any failure (no key, network down, timeout, bad response)
    ok is False and text is a short message safe to show the user.
    Never raises, so a flaky network can't crash the chat handler.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")

    # If the .env file is missing or the key was not filled in, tell the user
    # immediately rather than making a doomed API call that will just hang.
    if not api_key or api_key == "paste-your-key-here":
        return False, " No API key found. Add your OpenRouter key to the .env file and restart the app."

    # The Authorization header tells OpenRouter who we are.
    # NEVER hardcode the api_key here — always load it from the .env file.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",  # identifies our app to OpenRouter
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json={"model": DEFAULT_MODEL, "messages": messages},
            timeout=30,
        )
    except requests.exceptions.Timeout:
        print("OpenRouter request timed out.")
        return False, "The AI service took too long to respond. Please try again."
    except requests.exceptions.RequestException as error:
        print(f"OpenRouter request failed: {error!r}")
        return False, "I couldn't reach the AI service. Please check the connection and try again."

    try:
        result = response.json()
    except ValueError:
        print(f"OpenRouter returned non-JSON (HTTP {response.status_code}).")
        return False, f"Unexpected response from the AI service (HTTP {response.status_code})."

    if not isinstance(result, dict):
        return False, "Unexpected response from the AI service."

    # OpenRouter sometimes returns HTTP 200 but with an 'error' field instead
    # of 'choices' — this happens with a bad API key or an invalid request.
    if "error" in result:
        error = result["error"]
        message = error.get("message", "Unknown API error") if isinstance(error, dict) else str(error)
        return False, f" OpenRouter error: {message}"

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return False, f" Unexpected response from OpenRouter: {_short(result, 300)}"

    if not isinstance(content, str):
        return False, "The AI service returned an empty reply. Please try again."
    return True, content


def send_message(user_message, system_prompt="You are a helpful assistant."):
    """
    Send a message to the AI and return its response as a string (or a
    readable error message). Same behaviour as before, but safe against
    network failures. NOTE: no chat history -- each call starts fresh.
    """
    return call_llm(user_message, system_prompt)[1]


def extract_list_literal(text: str) -> str:
    # remove ```python ... ``` fences if present
    text = text.strip()
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    # keep only the part from the first [ to the last ]
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return text




# test line
# print(fill_template("Tester", "testing", "Say hi.", "Hello?"))
