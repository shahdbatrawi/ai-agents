"""
write_ops.py — the ONLY kinds of change the Database Write Expert may ask for.

The model never writes code. It returns a small JSON object such as
    {"operation": "delete_skill", "skill": "Python"}
and we check it here against a fixed list. Anything not on the list is refused.
"""

import json
import re

# operation name -> (required fields, needs approval before it runs?)
ALLOWED_OPERATIONS = {
    "add_skill":          ({"skill": str, "experience": str, "skill_level": int}, False),
    "update_skill_level": ({"skill": str, "skill_level": int},                    True),
    "delete_skill":       ({"skill": str},                                        True),
    "delete_all_skills":  ({},                                                    True),
}


def needs_approval(operation_name):
    return ALLOWED_OPERATIONS[operation_name][1]


def parse_operation(text):
    """
    Read the Write Expert's output as JSON and validate it. Returns a clean dict
    (only the known fields). Raises ValueError for anything else. Nothing the
    model wrote is ever executed.
    """
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text).strip())
    try:
        op = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError("the change request is not valid JSON")
    if not isinstance(op, dict):
        raise ValueError("the change request must be a JSON object")

    name = op.get("operation")
    if name not in ALLOWED_OPERATIONS:
        raise ValueError(f"operation not allowed: {name!r}")

    fields = ALLOWED_OPERATIONS[name][0]
    clean = {"operation": name}
    for field, kind in fields.items():
        value = op.get(field)
        if kind is int:
            if isinstance(value, str) and value.strip().isdigit():
                value = int(value)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
                raise ValueError(f"{field} must be a whole number from 1 to 10")
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} is missing")
            value = value.strip()
        clean[field] = value
    return clean