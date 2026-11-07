"""Validated skill operations and server-side approval handling."""

import sqlite3
from contextlib import closing
from threading import RLock


class SafeWrites:
    def __init__(self, db):
        self.db = db
        self._pending = {}
        self._lock = RLock()

    @staticmethod
    def _text(value, field):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text.")

        value = value.strip()

        if not value or len(value) > 200:
            raise ValueError(
                f"{field} must contain 1–200 characters."
            )

        return value

    def _validate(self, action):
        if not isinstance(action, dict):
            raise ValueError("Action must be a JSON object.")

        operation = action.get("operation")

        fields = {
            "add_skill": {
                "operation",
                "skill_name",
                "experience_name",
                "skill_level",
            },
            "delete_skill": {
                "operation",
                "skill_name",
                "experience_name",
            },
            "delete_all_skills": {"operation"},
        }

        if (
            not isinstance(operation, str)
            or operation not in fields
        ):
            raise ValueError("Unknown operation.")

        if set(action) - fields[operation]:
            raise ValueError("Unexpected action fields.")

        result = {"operation": operation}

        if operation != "delete_all_skills":
            result["skill_name"] = self._text(
                action.get("skill_name"),
                "skill_name",
            )

            experience = action.get("experience_name")

            result["experience_name"] = (
                None
                if experience is None
                else self._text(experience, "experience_name")
            )

        if operation == "add_skill":
            level = action.get("skill_level")

            if type(level) is not int or not 1 <= level <= 10:
                raise ValueError(
                    "skill_level must be an integer from 1 to 10."
                )

            result["skill_level"] = level

        return result

    def _resolve_experience(self, connection, name):
        if name is None:
            return None

        rows = connection.execute(
            "SELECT experience_id FROM experiences "
            "WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchall()

        if len(rows) != 1:
            raise ValueError(
                "Experience must match exactly one stored name."
            )

        return rows[0]["experience_id"]

    def submit(self, client_id, action):
        """Run an addition or store a deletion for approval."""
        with self._lock:
            self._pending.pop(client_id, None)
            action = self._validate(action)

            with closing(
                sqlite3.connect(self.db.db_path)
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")

                with connection:
                    operation = action["operation"]

                    if operation == "delete_all_skills":
                        rows = connection.execute(
                            "SELECT * FROM skills ORDER BY skill_id"
                        ).fetchall()

                    else:
                        experience_id = self._resolve_experience(
                            connection,
                            action["experience_name"],
                        )

                        if operation == "add_skill":
                            connection.execute(
                                "INSERT INTO skills "
                                "(experience_id, name, skill_level) "
                                "VALUES (?, ?, ?)",
                                (
                                    experience_id,
                                    action["skill_name"],
                                    action["skill_level"],
                                ),
                            )

                            return {
                                "state": "none",
                                "reply": (
                                    f"Added skill "
                                    f"'{action['skill_name']}'."
                                ),
                            }

                        sql = (
                            "SELECT * FROM skills "
                            "WHERE name = ? COLLATE NOCASE"
                        )
                        params = [action["skill_name"]]

                        if experience_id is not None:
                            sql += " AND experience_id = ?"
                            params.append(experience_id)

                        rows = connection.execute(
                            sql + " ORDER BY skill_id",
                            params,
                        ).fetchall()

                    if not rows:
                        return {
                            "state": "none",
                            "reply": "No matching skills found.",
                        }

                    snapshots = [dict(row) for row in rows]
                    descriptions = []

                    for row in snapshots:
                        experience = connection.execute(
                            "SELECT name FROM experiences "
                            "WHERE experience_id = ?",
                            (row["experience_id"],),
                        ).fetchone()

                        location = (
                            experience["name"]
                            if experience
                            else "general skills"
                        )

                        descriptions.append(
                            f"'{row['name']}' from '{location}' "
                            f"(skill ID {row['skill_id']})"
                        )

            self._pending[client_id] = snapshots

            return {
                "state": "waiting",
                "reply": (
                    "This will delete: "
                    + "; ".join(descriptions)
                    + ". Reply yes or no."
                ),
            }

    def answer(self, client_id, message):
        """Consume approval once without calling a model again."""
        with self._lock:
            snapshots = self._pending.pop(client_id, None)

            if snapshots is None:
                return None

            if message.strip().lower() != "yes":
                return {
                    "state": "cancelled",
                    "reply": "Cancelled. Nothing was changed.",
                }

            with closing(
                sqlite3.connect(self.db.db_path)
            ) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")

                with connection:
                    connection.execute("BEGIN IMMEDIATE")

                    # Cancel if a displayed record changed.
                    for snapshot in snapshots:
                        row = connection.execute(
                            "SELECT * FROM skills WHERE skill_id = ?",
                            (snapshot["skill_id"],),
                        ).fetchone()

                        if row is None or dict(row) != snapshot:
                            return {
                                "state": "cancelled",
                                "reply": (
                                    "The data changed. Please request "
                                    "the deletion again."
                                ),
                            }

                    # Delete only the exact IDs already shown.
                    connection.executemany(
                        "DELETE FROM skills WHERE skill_id = ?",
                        [
                            (snapshot["skill_id"],)
                            for snapshot in snapshots
                        ],
                    )

            return {
                "state": "approved",
                "reply": (
                    f"Deleted exactly {len(snapshots)} "
                    "approved skill(s)."
                ),
            }

    def cancel(self, client_id):
        """Clear pending approval when a client disconnects."""
        with self._lock:
            self._pending.pop(client_id, None)