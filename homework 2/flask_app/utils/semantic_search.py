"""Persistent embeddings and cosine-similarity search."""

import json
import math
import os

import requests


TABLES = {
    "institutions": (
        "inst_id",
        ("name", "department", "city", "state", "type"),
    ),
    "positions": (
        "position_id",
        ("title", "responsibilities"),
    ),
    "experiences": (
        "experience_id",
        ("name", "description"),
    ),
    "skills": (
        "skill_id",
        ("name",),
    ),
}


class EmbeddingError(RuntimeError):
    pass


def validate_vector(vector):
    if not isinstance(vector, list) or not vector:
        raise EmbeddingError("Embedding is empty or invalid.")

    if not all(
        type(value) in (int, float) and math.isfinite(value)
        for value in vector
    ):
        raise EmbeddingError("Embedding contains invalid numbers.")

    norm = math.hypot(*vector)

    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingError("Embedding has an invalid or zero norm.")

    return vector


class SemanticSearch:
    def __init__(self, db):
        self.db = db
        self.model = os.getenv("OPENROUTER_EMBEDDING_MODEL")

        if not self.model:
            raise EmbeddingError(
                "Missing OPENROUTER_EMBEDDING_MODEL in .env."
            )

        self.db.query("""
            CREATE TABLE IF NOT EXISTS embeddings (
                source_table TEXT NOT NULL,
                record_id INTEGER NOT NULL,
                model TEXT NOT NULL,
                embedded_text TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                PRIMARY KEY (source_table, record_id, model)
            )
        """)

    def embed(self, text):
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise EmbeddingError("Missing OPENROUTER_API_KEY.")

        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("Cannot embed empty text.")

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text,
                    "encoding_format": "float",
                },
                timeout=45,
            )
        except requests.RequestException:
            raise EmbeddingError(
                "Embedding service could not be reached."
            ) from None

        if not response.ok:
            raise EmbeddingError(
                f"Embedding request failed: HTTP "
                f"{response.status_code}. No matches were produced."
            )

        try:
            payload = response.json()

            if "error" in payload:
                raise EmbeddingError(
                    "Embedding API returned an error."
                )

            vector = payload["data"][0]["embedding"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise EmbeddingError(
                "Embedding API returned an invalid response."
            ) from None

        return validate_vector(vector)

    @staticmethod
    def record_text(table, row):
        fields = TABLES[table][1]

        return " | ".join(
            f"{field}: {row[field]}"
            for field in fields
            if row.get(field) is not None and str(row[field]).strip()
        )

    @staticmethod
    def validate_tables(tables):
        if (
            not isinstance(tables, (list, tuple))
            or not tables
            or any(
                not isinstance(table, str) or table not in TABLES
                for table in tables
            )
        ):
            raise ValueError("Invalid semantic-search tables.")

    def sync(self, tables):
        """Generate only missing or changed embeddings."""
        self.validate_tables(tables)

        for table in dict.fromkeys(tables):
            id_column = TABLES[table][0]
            records = self.db.query(
                f"SELECT * FROM {table} ORDER BY {id_column}"
            )

            cached = {
                row["record_id"]: row
                for row in self.db.query(
                    "SELECT * FROM embeddings "
                    "WHERE source_table = ? AND model = ?",
                    (table, self.model),
                )
            }

            live_ids = set()

            for record in records:
                record_id = record[id_column]
                live_ids.add(record_id)
                text = self.record_text(table, record)
                previous = cached.get(record_id)
                reusable = False

                if previous and previous["embedded_text"] == text:
                    try:
                        validate_vector(
                            json.loads(previous["vector_json"])
                        )
                        reusable = True
                    except (ValueError, TypeError, EmbeddingError):
                        reusable = False

                if reusable:
                    continue

                # A failed request raises before any vector is saved.
                vector = self.embed(text)

                self.db.query(
                    """
                    INSERT INTO embeddings (
                        source_table, record_id, model,
                        embedded_text, vector_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source_table, record_id, model)
                    DO UPDATE SET
                        embedded_text = excluded.embedded_text,
                        vector_json = excluded.vector_json
                    """,
                    (
                        table,
                        record_id,
                        self.model,
                        text,
                        json.dumps(vector, allow_nan=False),
                    ),
                )

            # Remove embeddings whose source records were deleted.
            for record_id in set(cached) - live_ids:
                self.db.query(
                    "DELETE FROM embeddings "
                    "WHERE source_table = ? AND record_id = ? "
                    "AND model = ?",
                    (table, record_id, self.model),
                )

    @staticmethod
    def cosine(left, right):
        validate_vector(left)
        validate_vector(right)

        if len(left) != len(right):
            raise EmbeddingError(
                "Embedding dimensions differ. Rebuild the index."
            )

        left_norm = math.hypot(*left)
        right_norm = math.hypot(*right)

        score = math.fsum(
            (a / left_norm) * (b / right_norm)
            for a, b in zip(left, right)
        )

        return max(-1.0, min(1.0, score))

    def search(self, question, tables, *, min_score, top_k=5):
        """Return ranked matches with their source and score."""
        self.validate_tables(tables)

        if (
            type(min_score) not in (int, float)
            or not math.isfinite(min_score)
            or not -1 <= min_score <= 1
        ):
            raise ValueError("min_score must be between -1 and 1.")

        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100.")

        self.sync(tables)
        query_vector = self.embed(question)
        matches = []

        for table in dict.fromkeys(tables):
            rows = self.db.query(
                "SELECT * FROM embeddings "
                "WHERE source_table = ? AND model = ?",
                (table, self.model),
            )

            for row in rows:
                try:
                    vector = json.loads(row["vector_json"])
                except (ValueError, TypeError):
                    raise EmbeddingError(
                        "Stored embedding is invalid."
                    ) from None

                score = self.cosine(query_vector, vector)

                if score >= min_score:
                    matches.append({
                        "table": table,
                        "record_id": row["record_id"],
                        "text": row["embedded_text"],
                        "score": score,
                    })

        matches.sort(
            key=lambda result: (
                -result["score"],
                result["table"],
                result["record_id"],
            )
        )

        return matches[:top_k]