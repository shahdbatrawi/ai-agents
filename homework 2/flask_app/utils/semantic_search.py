"""semantic_search.py - search resume records by meaning (embeddings + cosine)."""
import json
import os

from flask_app.utils.embeddings import embed_texts, cosine_similarity, EmbeddingError  # noqa: F401
from flask_app.utils.database import EMBED_SOURCES

DEFAULT_TOP_K = 5

# Column holding the exact, human-readable name of a record in each table.
NAME_COLUMNS = {"institutions": "name", "positions": "title",
                "experiences": "name", "skills": "name"}


def search_by_meaning(db, query, tables=None, top_k=DEFAULT_TOP_K, min_score=None):
    """
    Embed `query` and return the best matching records, ranked.

    Each result: {"table": ..., "id": ..., "name": <exact name stored in the DB>,
                  "text": <embedded text>, "score": <cosine>}
    - tables:    only search these tables (default: all embedded tables)
    - min_score: results below this are dropped. Default comes from SEARCH_MIN_SCORE.
    Raises EmbeddingError if the query itself cannot be embedded (never invents matches).
    """
    if min_score is None:
        min_score = float(os.getenv("SEARCH_MIN_SCORE", "0.0"))
    query = (query or "").strip()
    if not query:
        return []

    if tables:
        unknown = [t for t in tables if t not in EMBED_SOURCES]
        if unknown:
            raise ValueError(f"Cannot search unknown table(s): {unknown}")

    query_vec = embed_texts([query])[0]          # may raise EmbeddingError

    sql = "SELECT source_table, source_id, text, vector FROM embeddings WHERE model = ?"
    params = [os.getenv("EMBEDDING_MODEL")]
    if tables:
        sql += " AND source_table IN (" + ",".join("?" for _ in tables) + ")"
        params += list(tables)

    results = []
    for row in db.query(sql, tuple(params)):
        vec = json.loads(row["vector"])
        if len(vec) != len(query_vec):           # vector from a different model size
            continue
        score = cosine_similarity(query_vec, vec)
        if score >= min_score:
            results.append({"table": row["source_table"], "id": row["source_id"],
                            "text": row["text"], "score": round(score, 4)})

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:top_k]

    # Add the exact stored name, so a later step can use it in SQL.
    for r in results:
        name = r["text"]
        if r["table"] in EMBED_SOURCES and r["table"] in NAME_COLUMNS:
            id_col = EMBED_SOURCES[r["table"]][0]
            rows = db.query(
                f"SELECT {NAME_COLUMNS[r['table']]} AS name FROM {r['table']} WHERE {id_col} = ?",
                (r["id"],),
            )
            if rows:
                name = rows[0]["name"]
        r["name"] = name
    return results