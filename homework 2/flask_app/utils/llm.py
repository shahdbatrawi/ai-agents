"""Validated expert routing, semantic retrieval, and safe writes."""

import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import requests

from flask_app.utils.semantic_routes import run_semantic_request


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

ALLOWED_EXPERTS = {
    "Database Read Expert",
    "Database Write Expert",
    "Content Expert",
    "Semantic Search Expert",
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "enum": sorted(ALLOWED_EXPERTS),
                    },
                    "message": {"type": "string"},
                },
                "required": ["role", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reason", "steps"],
    "additionalProperties": False,
}

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": [
                "add_skill",
                "delete_skill",
                "delete_all_skills",
                "unsupported",
            ],
        },
        "skill_name": {"type": ["string", "null"]},
        "experience_name": {"type": ["string", "null"]},
        "skill_level": {"type": ["integer", "null"]},
    },
    "required": [
        "operation",
        "skill_name",
        "experience_name",
        "skill_level",
    ],
    "additionalProperties": False,
}


def send_message(
    user_message,
    system_prompt="You are a helpful assistant.",
    *,
    json_mode=False,
    response_schema=None,
):
    """Call OpenRouter with optional structured JSON output."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_CHAT_MODEL")

    if not api_key:
        raise ValueError("Missing OPENROUTER_API_KEY in .env.")

    if not model:
        raise ValueError("Missing OPENROUTER_CHAT_MODEL in .env.")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0,
    }

    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "expert_response",
                "strict": True,
                "schema": response_schema,
            },
        }
        payload["provider"] = {"require_parameters": True}

    elif json_mode:
        payload["response_format"] = {"type": "json_object"}
        payload["provider"] = {"require_parameters": True}

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )
    except requests.RequestException:
        raise RuntimeError(
            "Could not reach OpenRouter. Please try again."
        ) from None

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter request failed (HTTP {response.status_code})."
        )

    try:
        result = response.json()

        if "error" in result:
            raise RuntimeError(
                "OpenRouter reported an API error. "
                "Check model availability, permissions, and limits."
            )

        content = result["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(
            "OpenRouter returned an invalid response."
        ) from None

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The model returned an empty response.")

    return content.strip()


def strip_code_fences(text):
    """Remove one surrounding Markdown code block."""
    text = text.strip()

    match = re.fullmatch(
        r"```[^\n]*\n(.*?)\n?```",
        text,
        flags=re.DOTALL,
    )

    return match.group(1).strip() if match else text


def parse_json(text):
    """Read model output as data, never executable code."""
    cleaned = strip_code_fences(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        print(
            "[JSON ERROR]",
            f"line={error.lineno}, column={error.colno}: {error.msg}",
            flush=True,
        )
        print(
            "[INVALID MODEL OUTPUT]",
            repr(cleaned[:6000]),
            flush=True,
        )

        raise ValueError(
            "The model returned invalid JSON. Please try again."
        ) from None


def normalize_write_action(action):
    """Check the response shape before passing it to SafeWrites."""
    expected_fields = {
        "operation",
        "skill_name",
        "experience_name",
        "skill_level",
    }

    if not isinstance(action, dict) or set(action) != expected_fields:
        raise ValueError("Invalid write action structure.")

    operation = action["operation"]

    if not isinstance(operation, str):
        raise ValueError("Invalid operation name.")

    if operation == "unsupported":
        raise ValueError("This database change is not supported.")

    if operation == "delete_all_skills":
        if any(
            action[field] is not None
            for field in ("skill_name", "experience_name", "skill_level")
        ):
            raise ValueError(
                "Delete-all must not contain item values."
            )

        return {"operation": operation}

    if operation == "delete_skill":
        if action["skill_level"] is not None:
            raise ValueError(
                "A deletion must not specify a skill level."
            )

        return {
            "operation": operation,
            "skill_name": action["skill_name"],
            "experience_name": action["experience_name"],
        }

    if operation == "add_skill":
        return action

    raise ValueError("Unknown write operation.")


def expert_output(db, role, message):
    """Build prompts and request the appropriate response schema."""
    roles = db.getLLMRoles()

    if role not in roles:
        raise ValueError(f"Missing expert configuration: {role}")

    config = roles[role]

    sections = [
        f"You are {role}.",
        config["domain"],
        config["specific_instructions"],
        config.get("background_context") or "",
        config.get("few_shot_examples") or "",
    ]

    if role == "Content Expert":
        sections.append("Resume data:\n" + db.getResumeText())

    schema = None

    if role == "Orchestrator":
        schema = PLAN_SCHEMA

    elif role == "Database Write Expert":
        schema = WRITE_SCHEMA

        sections.append(
            "OUTPUT FORMAT UPDATE: Always return all four JSON fields: "
            "operation, skill_name, experience_name, skill_level. "
            "For add_skill, provide the skill name, an experience name "
            "or null, and an integer skill level from 1 to 10 "
            "(default 5 if unspecified). "
            "For delete_skill, provide the skill name and an experience "
            "name or null; skill_level MUST be null. "
            "For delete_all_skills, all three value fields MUST be null. "
            "For an unsupported request, operation MUST be unsupported "
            "and all three value fields MUST be null. "
            "Do not substitute a supported action for an unsupported one. "
            "This output format replaces the earlier examples' format. "
            "You propose an operation; you never execute it."
        )

    output = send_message(
        message,
        "\n\n".join(sections),
        response_schema=schema,
    )

    if role == "Database Write Expert":
        action = normalize_write_action(parse_json(output))
        return json.dumps(action)

    return output


def execute_read_query(db, sql):
    """Run generated SELECT SQL through a read-only connection."""
    sql = strip_code_fences(sql)

    if not re.match(r"^SELECT\b", sql, flags=re.IGNORECASE):
        raise ValueError("Read Expert must return a SELECT query.")

    uri = Path(db.db_path).resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")

        budget = [0]

        def check_budget():
            budget[0] += 1
            return int(budget[0] > 1000)

        connection.set_progress_handler(check_budget, 1000)

        cursor = connection.execute(sql)
        rows = cursor.fetchmany(501)

        if len(rows) > 500:
            raise ValueError(
                "Too many results. Please ask a narrower question."
            )

        return [dict(row) for row in rows]


def validate_plan(plan):
    """Validate the entire plan before executing any step."""
    if not isinstance(plan, dict):
        raise ValueError("The plan must be a JSON object.")

    if set(plan) != {"reason", "steps"}:
        raise ValueError("Unexpected plan fields.")

    reason = plan["reason"]
    steps = plan["steps"]

    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 1000
    ):
        raise ValueError("Invalid routing reason.")

    if not isinstance(steps, list) or not 1 <= len(steps) <= 4:
        raise ValueError("The plan must contain 1-4 steps.")

    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid plan step.")

        if set(step) != {"role", "message"}:
            raise ValueError("Unexpected step fields.")

        role = step["role"]
        message = step["message"]

        if not isinstance(role, str) or role not in ALLOWED_EXPERTS:
            raise ValueError("Unknown expert in the plan.")

        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > 8000
        ):
            raise ValueError("Invalid expert message.")

    exclusive_roles = {
        "Database Write Expert",
        "Semantic Search Expert",
    }

    if len(steps) != 1 and any(
        step["role"] in exclusive_roles for step in steps
    ):
        raise ValueError(
            "A write or semantic request must be its own plan."
        )

    return plan


def choose_plan(db, message):
    """Use routing rules, then model planning for other requests."""
    text = message.strip().rstrip("?.!").strip()

    # Routing selects the expert, not whether a write is approved.
    write_request = re.match(
        r"^(?:please\s+)?"
        r"(?:add|remove|delete|erase|clear|empty|clean(?:\s+up)?)\b",
        text,
        flags=re.IGNORECASE,
    )

    if write_request:
        return validate_plan({
            "reason": (
                "An explicit change request goes to the Write Expert. "
                "The write executor determines whether approval is required."
            ),
            "steps": [{
                "role": "Database Write Expert",
                "message": message,
            }],
        })

    exact_patterns = [
        (
            r"(?:list|show|display)\s+(?:all\s+)?my\s+"
            r"(?:skills|positions|experiences|institutions)"
        ),
        (
            r"how\s+many\s+"
            r"(?:skills|positions|experiences|institutions)"
            r"\s+do\s+i\s+have"
        ),
        r"what\s+(?:all\s+)?skills\s+do\s+i\s+have",
    ]

    if any(
        re.fullmatch(pattern, text, flags=re.IGNORECASE)
        for pattern in exact_patterns
    ):
        return validate_plan({
            "reason": (
                "An exact listing or count requires database rows, "
                "not semantic similarity."
            ),
            "steps": [{
                "role": "Database Read Expert",
                "message": message,
            }],
        })

    institution_patterns = [
        (r"find\s+my\s+(.+?)\s+experience", False),
        (r"what\s+did\s+i\s+do\s+at\s+(.+)", True),
    ]

    for pattern, lookup in institution_patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)

        if match:
            entity = match.group(1).strip()

            return validate_plan({
                "reason": (
                    "Institution lookup uses semantic name resolution"
                    + (
                        " followed by a dependent database lookup."
                        if lookup else "."
                    )
                ),
                "steps": [{
                    "role": "Semantic Search Expert",
                    "message": json.dumps({
                        "query": f"{entity} experience",
                        "tables": ["institutions"],
                        "lookup_experiences": lookup,
                    }),
                }],
            })

    category_match = re.fullmatch(
        r"what\s+(.+?)\s+skills\s+do\s+i\s+have",
        text,
        flags=re.IGNORECASE,
    )

    if category_match:
        category = category_match.group(1).strip()

        if category.casefold() not in {"all", "listed", "stored"}:
            return validate_plan({
                "reason": (
                    "A skill category requires semantic search "
                    "restricted to the skills table."
                ),
                "steps": [{
                    "role": "Semantic Search Expert",
                    "message": json.dumps({
                        "query": f"{category} skills",
                        "tables": ["skills"],
                        "lookup_experiences": False,
                    }),
                }],
            })

    return validate_plan(
        parse_json(expert_output(db, "Orchestrator", message))
    )


def summarize_results(message, results):
    """Format retrieved data without another model call."""
    if isinstance(results, dict):
        if results.get("outcome") == "not_found":
            return "No matching records found."

        institution = results.get("institution")

        if institution:
            lines = [f"At {institution['name']}:"]
            rows = results.get("experiences", [])

            if not rows:
                lines.append("No positions or experiences were found.")
                return "\n".join(lines)

            shown_positions = set()

            for row in rows:
                position_id = row["position_id"]

                if position_id not in shown_positions:
                    shown_positions.add(position_id)
                    lines.append(f"\nPosition: {row['title']}")

                    if row.get("responsibilities"):
                        lines.append(row["responsibilities"])

                if row.get("experience_name"):
                    line = f"- {row['experience_name']}"

                    if row.get("description"):
                        line += f": {row['description']}"

                    lines.append(line)

            return "\n".join(lines)

        matches = results.get("matches", [])

        if not matches:
            return "No matching records found."

        lines = ["Found these matching records:"]

        for match in matches:
            lines.append(
                f"- {match['text']} "
                f"({match['table']} #{match['record_id']}, "
                f"score {match['score']:.4f})"
            )

        return "\n".join(lines)

    lines = []

    for result in results:
        if "answer" in result:
            lines.append(str(result["answer"]))
            continue

        for row in result.get("rows", []):
            lines.append(
                "- " + "; ".join(
                    f"{key}: {value}"
                    for key, value in row.items()
                    if value is not None
                )
            )

    return "\n".join(lines) if lines else "No matching records found."


def handle_ai_chat_request(
    db,
    role,
    message,
    *,
    writer=None,
    client_id=None,
    trace=None,
):
    """Run a validated plan through explicitly allowed experts."""
    def log(event, **details):
        if trace is not None:
            trace(event, **details)

    if role != "Orchestrator":
        raise ValueError("Chat requests must enter through Orchestrator.")

    plan = choose_plan(db, message)

    log(
        "route",
        experts=[step["role"] for step in plan["steps"]],
        reason=plan["reason"],
        approval="none",
    )

    results = []

    for step in plan["steps"]:
        expert = step["role"]
        request_text = step["message"]

        log("expert_started", expert=expert)

        if expert == "Semantic Search Expert":
            specification = parse_json(request_text)
            retrieved = run_semantic_request(db, specification, log)

            if retrieved["outcome"] == "not_found":
                return "No matching records found."

            return summarize_results(message, retrieved)

        if results:
            request_text += (
                "\n\nResults from earlier steps:\n"
                + json.dumps(results, ensure_ascii=False)
            )

        output = expert_output(db, expert, request_text)

        if expert == "Database Write Expert":
            if writer is None or client_id is None:
                raise ValueError("Safe write context is missing.")

            action = parse_json(output)
            result = writer.submit(client_id, action)

            log(
                "write",
                operation=action.get("operation"),
                approval=result["state"],
                outcome=result["reply"],
            )

            return result["reply"]

        if expert == "Database Read Expert":
            rows = execute_read_query(db, output)

            log(
                "read",
                sql=strip_code_fences(output),
                row_count=len(rows),
                approval="none",
            )

            results.append({"expert": expert, "rows": rows})
        else:
            results.append({"expert": expert, "answer": output})

    if len(results) == 1 and "answer" in results[0]:
        return results[0]["answer"]

    if all(
        "rows" in result and not result["rows"]
        for result in results
    ):
        return "No matching records found."

    return summarize_results(message, results)