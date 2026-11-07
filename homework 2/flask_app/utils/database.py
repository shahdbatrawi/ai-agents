"""SQLite database access and persistent startup initialization."""

import csv
import os
import sqlite3
from contextlib import closing


DATABASE_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "database")
)

DB_PATH = os.path.join(DATABASE_FOLDER, "resume.db")

TABLE_ORDER = [
    "institutions",
    "positions",
    "experiences",
    "skills",
    "llm_roles",
]


class database:
    def __init__(self):
        self.db_path = DB_PATH

    def query(self, sql, params=()):
        """Execute SQL with bound parameters and return any result rows."""
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.row_factory = sqlite3.Row

            with connection:
                cursor = connection.execute(sql, params)

                if cursor.description is not None:
                    return [dict(row) for row in cursor.fetchall()]

                return []

    def createTables(self, purge=False):
        """
        Preserve existing resume tables and refresh role configuration.

        New tables are seeded only once. Initialization runs in one
        transaction so a failed CSV load does not leave partial changes.
        """
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")

            with connection:
                connection.execute("BEGIN IMMEDIATE")

                if purge:
                    for table in reversed(TABLE_ORDER):
                        connection.execute(
                            f'DROP TABLE IF EXISTS "{table}"'
                        )

                existing_tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table'"
                    )
                }

                for table in TABLE_ORDER:
                    sql_file = os.path.join(
                        DATABASE_FOLDER,
                        "create_tables",
                        f"{table}.sql",
                    )

                    with open(sql_file, encoding="utf-8-sig") as file:
                        connection.execute(file.read())

                    if table != "llm_roles":
                        if table not in existing_tables:
                            self._seed_table(connection, table)

                self._refresh_llm_roles(connection)

        print("Database initialized; existing resume data preserved.")

    def _read_seed_rows(self, table):
        """Read a seed CSV and convert NULL strings to None."""
        csv_file = os.path.join(
            DATABASE_FOLDER,
            "initial_data",
            f"{table}.csv",
        )

        with open(
            csv_file, encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)
            columns = reader.fieldnames

            if not columns:
                raise ValueError(f"{table}.csv has no header.")

            rows = []
            for row in reader:
                if None in row or any(
                    value is None for value in row.values()
                ):
                    raise ValueError(
                        f"Malformed row in {table}.csv."
                    )

                rows.append({
                    column: None if value == "NULL" else value
                    for column, value in row.items()
                })

        return columns, rows

    def _seed_table(self, connection, table):
        """Load a newly created resume table."""
        columns, rows = self._read_seed_rows(table)

        allowed_columns = {
            row[1]
            for row in connection.execute(
                f'PRAGMA table_info("{table}")'
            )
        }

        if not set(columns).issubset(allowed_columns):
            raise ValueError(
                f"Unknown columns in {table}.csv."
            )

        column_sql = ", ".join(
            f'"{column}"' for column in columns
        )
        placeholders = ", ".join("?" for _ in columns)

        sql = (
            f'INSERT INTO "{table}" ({column_sql}) '
            f"VALUES ({placeholders})"
        )

        connection.executemany(
            sql,
            [
                tuple(row[column] for column in columns)
                for row in rows
            ],
        )

        print(f"  Loaded initial data: {table}")

    def _refresh_llm_roles(self, connection):
        """Update existing role prompts and insert newly added roles."""
        columns, rows = self._read_seed_rows("llm_roles")

        required = {
            "role",
            "domain",
            "specific_instructions",
        }

        if not required.issubset(columns):
            raise ValueError(
                "llm_roles.csv is missing required columns."
            )

        sql = """
            INSERT INTO llm_roles (
                role,
                domain,
                specific_instructions,
                background_context,
                few_shot_examples
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(role) DO UPDATE SET
                domain = excluded.domain,
                specific_instructions =
                    excluded.specific_instructions,
                background_context =
                    excluded.background_context,
                few_shot_examples =
                    excluded.few_shot_examples
        """

        connection.executemany(
            sql,
            [
                (
                    row["role"],
                    row["domain"],
                    row["specific_instructions"],
                    row.get("background_context"),
                    row.get("few_shot_examples"),
                )
                for row in rows
            ],
        )

        print("  Refreshed LLM role configuration.")

    def getResumeData(self):
        """Return the resume as nested institutions and positions."""
        resume = {}

        for institution in self.query(
            "SELECT * FROM institutions"
        ):
            inst_id = institution["inst_id"]
            resume[inst_id] = dict(institution)
            resume[inst_id]["positions"] = {}

            positions = self.query(
                "SELECT * FROM positions "
                "WHERE inst_id = ? "
                "ORDER BY start_date DESC",
                (inst_id,),
            )

            for position in positions:
                pos_id = position["position_id"]
                position_data = dict(position)
                position_data["experiences"] = {}
                resume[inst_id]["positions"][pos_id] = position_data

                experiences = self.query(
                    "SELECT * FROM experiences "
                    "WHERE position_id = ? "
                    "ORDER BY start_date DESC",
                    (pos_id,),
                )

                for experience in experiences:
                    exp_id = experience["experience_id"]
                    experience_data = dict(experience)
                    experience_data["skills"] = {}
                    position_data["experiences"][exp_id] = (
                        experience_data
                    )

                    skills = self.query(
                        "SELECT * FROM skills "
                        "WHERE experience_id = ?",
                        (exp_id,),
                    )

                    for skill in skills:
                        skill_id = skill["skill_id"]
                        experience_data["skills"][skill_id] = (
                            dict(skill)
                        )

        self._format_dates(resume)
        return resume

    def _format_dates(self, resume):
        """Format dates for the resume page."""
        for institution in resume.values():
            for position in institution["positions"].values():
                position["start_date"] = self._short_date(
                    position["start_date"]
                )
                position["end_date"] = (
                    self._short_date(position["end_date"])
                    or "Present"
                )

                for experience in (
                    position["experiences"].values()
                ):
                    experience["start_date"] = self._short_date(
                        experience["start_date"]
                    )
                    experience["end_date"] = (
                        self._short_date(experience["end_date"])
                        or ""
                    )

    def _short_date(self, date_string):
        if date_string:
            return str(date_string)[:7]
        return None

    def getResumeText(self):
        """Return a plain-text representation of the resume."""
        resume = self.getResumeData()
        lines = []

        for institution in resume.values():
            lines.append(
                f"\nInstitution: {institution['name']} "
                f"({institution['type']}) - "
                f"{institution.get('city', '')}, "
                f"{institution.get('state', '')}"
            )

            for position in institution["positions"].values():
                lines.append(
                    f"  Position: {position['title']} "
                    f"({position['start_date']} to "
                    f"{position['end_date']})"
                )
                lines.append(
                    "  Responsibilities: "
                    f"{position.get('responsibilities', '')}"
                )

                for experience in (
                    position["experiences"].values()
                ):
                    lines.append(
                        f"    Experience: {experience['name']} - "
                        f"{experience.get('description', '')}"
                    )

                    for skill in experience["skills"].values():
                        lines.append(
                            f"      Skill: {skill['name']} "
                            f"(level {skill['skill_level']}/10)"
                        )

        return "\n".join(lines)

    def getLLMRoles(self):
        """Return role configuration indexed by role name."""
        rows = self.query("SELECT * FROM llm_roles")
        return {row["role"]: row for row in rows}

    def insertRows(self, table, columns, values):
        """
        Legacy HW1 insert interface.

        This will be replaced by validated write operations
        when implementing the approval requirement.
        """
        value_sql = []
        bound_params = []

        for value in values:
            if (
                isinstance(value, str)
                and value.strip().startswith("(SELECT")
            ):
                value_sql.append(value)
            else:
                value_sql.append("?")
                bound_params.append(value)

        sql = (
            f"INSERT INTO {table} "
            f"({', '.join(columns)}) "
            f"VALUES ({', '.join(value_sql)})"
        )

        self.query(sql, tuple(bound_params))