"""Test write approval using a temporary database."""

import importlib.util
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace


root = Path(__file__).resolve().parent
source = root / "flask_app" / "utils" / "safe_writes.py"

spec = importlib.util.spec_from_file_location(
    "safe_writes_test", source
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


with tempfile.TemporaryDirectory() as temporary:
    db_path = str(Path(temporary) / "test.db")

    # Close the connection explicitly so Windows can delete the file.
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE experiences "
                "(experience_id INTEGER PRIMARY KEY, name TEXT)"
            )

            connection.execute(
                "CREATE TABLE skills ("
                "skill_id INTEGER PRIMARY KEY, "
                "experience_id INTEGER, "
                "name TEXT, "
                "skill_level INTEGER)"
            )

            connection.execute(
                "INSERT INTO experiences VALUES (1, 'CSE 847')"
            )

            connection.executemany(
                "INSERT INTO skills VALUES (?, ?, ?, ?)",
                [
                    (1, 1, "Python", 8),
                    (2, None, "Public Speaking", 6),
                ],
            )

    writer = module.SafeWrites(
        SimpleNamespace(db_path=db_path)
    )

    def skill_ids():
        with closing(sqlite3.connect(db_path)) as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT skill_id FROM skills ORDER BY skill_id"
                ).fetchall()
            ]

    action = {
        "operation": "delete_skill",
        "skill_name": "Python",
        "experience_name": "CSE 847",
    }

    # Requesting deletion must not execute it.
    result = writer.submit("student", action)
    print(result["reply"])

    assert result["state"] == "waiting"
    assert skill_ids() == [1, 2]
    print("PASS: Request alone does not delete anything.")

    # A clear no cancels the pending deletion.
    result = writer.answer("student", "no")

    assert result["state"] == "cancelled"
    assert skill_ids() == [1, 2]
    print("PASS: no preserves the database.")

    # An unclear answer cancels; a later yes has nothing to approve.
    writer.submit("student", action)
    result = writer.answer("student", "maybe")

    assert result["state"] == "cancelled"
    assert writer.answer("student", "yes") is None
    assert skill_ids() == [1, 2]
    print("PASS: maybe cancels; a later yes cannot approve.")

    # Changing the subject invalidates the pending deletion.
    writer.submit("student", action)
    result = writer.answer("student", "List my skills")

    assert result["state"] == "cancelled"
    assert writer.answer("student", "yes") is None
    assert skill_ids() == [1, 2]
    print("PASS: Changing the subject cancels old approval.")

    # Approval belongs to the client that requested the action.
    writer.submit("student", action)

    assert writer.answer("other-client", "yes") is None
    assert skill_ids() == [1, 2]
    print("PASS: Another client cannot approve.")

    # Approval executes the displayed deletion exactly once.
    result = writer.answer("student", "yes")

    assert result["state"] == "approved"
    assert skill_ids() == [2]
    assert writer.answer("student", "yes") is None
    print("PASS: yes deletes only the displayed skill, once.")

    # Deleting all skills must also wait for approval.
    result = writer.submit(
        "student",
        {"operation": "delete_all_skills"},
    )

    assert result["state"] == "waiting"
    assert skill_ids() == [2]

    result = writer.answer("student", "no")

    assert result["state"] == "cancelled"
    assert skill_ids() == [2]
    print("PASS: Delete-all also requires approval.")

print("Safety checks finished; app database was not changed.")