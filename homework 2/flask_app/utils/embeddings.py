
import json
import math
import os
import sqlite3

import requests

# ----------------------------------------------------------------------
# Settings (single source of truth for search and storage)
# ----------------------------------------------------------------------
MIN_SCORE = 0.35  # a record is kept when its cosine similarity is >= this value
DEFAULT_LIMIT = 5  # maximum number of search results returned
BATCH_SIZE = 50  # texts sent to the embeddings API per call
ENTITY_TYPES = ("institution", "position", "experience", "skill")


def get_embeddings(texts):
    """
    Get the embeddings for a list of texts using the OpenRouter API.

    Args:
        texts (list): A list of input texts to be embedded.

    Returns:
        list | None: A list of embedding vectors (same order as the input),
        or None if anything went wrong. It never returns partial or
        made-up vectors.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("EMBEDDING_MODEL")

    if not api_key or not model:
        print("Embedding failed: API key or model is not set in environment variables.")
        return None

    if texts is None or not isinstance(texts, list) or len(texts) == 0:
        print("Embedding failed: input texts must be a non-empty list.")
        return None

    for text in texts:
        if not isinstance(text, str) or not text.strip():
            print("Embedding failed: each input text must be a non-empty string.")
            return None
    try:
        # OpenRouter rejects empty input strings with HTTP 400, and accepts
        # whitespace-only strings, so the texts are checked above.
        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": texts},
            timeout=30,
        )

    except requests.exceptions.Timeout:
        print("Embedding failed: request timed out.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Embedding failed: request error: {e}")
        return None

    if response.status_code != 200:
        print(f"Embedding failed: HTTP status {response.status_code}.")
        return None

    try:
        result = response.json()
    except ValueError:
        print("Embedding failed: invalid JSON response.")
        return None

    if not isinstance(result, dict):
        print("Embedding failed: invalid response format.")
        return None

    if "error" in result:
        print("Embedding failed: API returned an error.")
        return None

    if "data" not in result:
        print("Embedding failed: response is missing data.")
        return None

    items = result["data"]

    if not isinstance(items, list):
        print("Embedding failed: response data is invalid.")
        return None

    if len(items) != len(texts):
        print(
            "Embedding failed: number of vectors does not match "
            "number of input texts."
        )
        return None

    embeddings = [None] * len(texts)

    for item in items:
        if not isinstance(item, dict):
            print("Embedding failed: invalid embedding item.")
            return None

        if "index" not in item or "embedding" not in item:
            print("Embedding failed: embedding item is missing index or embedding.")
            return None

        index = item["index"]
        vector = item["embedding"]

        if not isinstance(index, int) or index < 0 or index >= len(texts):
            print("Embedding failed: invalid embedding index.")
            return None

        if embeddings[index] is not None:
            print("Embedding failed: duplicate embedding index.")
            return None

        if not isinstance(vector, list) or len(vector) == 0:
            print("Embedding failed: embedding vector is empty.")
            return None

        if all(value == 0 for value in vector):
            print("Embedding failed: embedding vector contains only zeros.")
            return None

        embeddings[index] = vector

    if any(vector is None for vector in embeddings):
        print("Embedding failed: one or more embeddings are missing.")
        return None

    return embeddings


def get_embedding_vectors(text):
    """
    Get the embedding vector for a single text using the OpenRouter API.

    Args:
        text (str): The input text to be embedded.

    Returns:
        list | None: The embedding vector, or None on failure.
    """
    vectors = get_embeddings([text])
    return vectors[0] if vectors else None


def get_embedding_records(db):
    """
    Read records from the four searchable tables and prepare the text
    that will be converted into an embedding.

    Args:
        db: The database object (must have a query() method).

    Returns:
        list: A list of dictionaries. Each dictionary contains:
            - entity_type: the source TABLE name (plural, e.g. "skills")
            - id: the record ID
            - text: the text that will be embedded
    """

    records = []

    # institutions
    institution_rows = db.query("SELECT inst_id, name, city, state FROM institutions")
    for row in institution_rows:
        institution_id = row["inst_id"]
        name = clean_text(row["name"])
        city = clean_text(row["city"])
        state = clean_text(row["state"])
        text = build_text(name, city, state)
        if text:
            records.append(
                {"entity_type": "institutions", "id": institution_id, "text": text}
            )

    # positions
    position_rows = db.query(
        "SELECT p.position_id, p.title, p.responsibilities, i.name AS institution_name "
        "FROM positions p "
        "JOIN institutions i ON p.inst_id = i.inst_id"
    )
    for row in position_rows:
        position_id = row["position_id"]
        title = clean_text(row["title"])
        responsibilities = clean_text(row["responsibilities"])
        institution_name = clean_text(row["institution_name"])
        text = build_text(title, responsibilities, institution_name)
        if text:
            records.append(
                {"entity_type": "positions", "id": position_id, "text": text}
            )

    # skills
    skill_rows = db.query("SELECT skill_id, name FROM skills")
    for row in skill_rows:
        skill_id = row["skill_id"]
        name = clean_text(row["name"])
        text = build_text(name)
        if text:
            records.append({"entity_type": "skills", "id": skill_id, "text": text})

    # experiences
    experience_rows = db.query(
        "SELECT e.experience_id, e.name AS experience_name, e.description, "
        "p.title, i.name AS institution_name "
        "FROM experiences e "
        "JOIN positions p ON e.position_id = p.position_id "
        "JOIN institutions i ON p.inst_id = i.inst_id"
    )
    for row in experience_rows:
        experience_id = row["experience_id"]
        name = clean_text(row["experience_name"])
        description = clean_text(row["description"])
        position_title = clean_text(row["title"])
        institution_name = clean_text(row["institution_name"])
        text = build_text(name, position_title, institution_name, description)
        if text:
            records.append(
                {"entity_type": "experiences", "id": experience_id, "text": text}
            )

    return records


def create_and_store_embeddings(db):
    """
    Bring the `embeddings` table in line with the database (a "sync").

    Only the work that is needed is done, so it is safe to call on every
    start and after every change:
      - records with no embedding yet are embedded;
      - records whose text changed are embedded again;
      - records embedded with a different model than EMBEDDING_MODEL are
        embedded again;
      - embeddings whose record no longer exists are deleted.

    A batch that fails (API error, bad vector, ...) stores nothing and is
    retried on the next call. Nothing made-up is ever stored.

    Args:
        db: The database object (needs query() and db_path).

    Returns:
        bool: True if every record now has an up-to-date embedding,
        False if something could not be embedded or the setup is missing.
    """
    model = os.getenv("EMBEDDING_MODEL")

    if not model:
        print("Embedding sync failed: EMBEDDING_MODEL is missing.")
        return False

    # What should exist: {(entity_type, entity_id): text}
    desired = {}
    for record in get_embedding_records(db):
        entity_type = table_name_to_entity_type(record["entity_type"])

        if entity_type is None:
            print(f"Embedding sync: skipping unknown table {record['entity_type']}.")
            continue

        desired[(entity_type, record["id"])] = record["text"]

    # What exists now: {(entity_type, entity_id): (text, model)}
    stored = {}
    for row in db.query(
        "SELECT entity_type, entity_id, embed_text, model FROM embeddings"
    ):
        stored[(row["entity_type"], row["entity_id"])] = (
            row["embed_text"],
            row["model"],
        )

    to_embed = [
        key
        for key, text in desired.items()
        if key not in stored or stored[key][0] != text or stored[key][1] != model
    ]
    orphans = [key for key in stored if key not in desired]

    new_rows = []
    failed = 0
    api_calls = 0

    for start in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[start : start + BATCH_SIZE]
        texts = [desired[key] for key in batch]

        api_calls += 1
        vectors = get_embeddings(texts)

        if vectors is None:
            print(f"Embedding sync: a batch of {len(batch)} record(s) was not stored.")
            failed += len(batch)
            continue

        for key, vector in zip(batch, vectors):
            new_rows.append(
                (key[0], key[1], desired[key], json.dumps(vector), model)
            )

    if new_rows or orphans:
        # One connection and one commit for all the writes.
        connection = sqlite3.connect(db.db_path)
        try:
            connection.executemany(
                "DELETE FROM embeddings WHERE entity_type = ? AND entity_id = ?",
                orphans,
            )
            connection.executemany(
                """
                INSERT INTO embeddings (
                    entity_type,
                    entity_id,
                    embed_text,
                    vector,
                    model
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id)
                DO UPDATE SET
                    embed_text = excluded.embed_text,
                    vector = excluded.vector,
                    model = excluded.model
                """,
                new_rows,
            )
            connection.commit()
        finally:
            connection.close()

    print(
        f"Embedding sync: {len(new_rows)} written, {len(orphans)} removed, "
        f"{failed} failed, {api_calls} API call(s)."
    )

    return failed == 0


def cosine_similarity(vector_a, vector_b):
    """
    Calculate the cosine similarity between two vectors.

    Args:
        vector_a (list): The first vector.
        vector_b (list): The second vector.

    Returns:
        float: The cosine similarity between the two vectors
        (0.0 if either vector is empty, they differ in length, or one is zero).
    """
    if not vector_a or not vector_b:
        return 0.0

    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for a, b in zip(vector_a, vector_b):
        dot_product += a * b
        norm_a += a * a
        norm_b += b * b

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search_by_meaning(
    db, query_text, limit=DEFAULT_LIMIT, min_score=MIN_SCORE, tables=None
):
    """
    Search stored embeddings using cosine similarity.

    Only embeddings made with the current EMBEDDING_MODEL are compared, so
    vectors from different models are never mixed.

    Args:
        db: The database object.
        query_text (str): The user's search text.
        limit (int): The maximum number of results to return.
        min_score (float): The minimum similarity score required.
        tables (list | str | None): Optional filter, e.g. ["skills"] or
            ["skill", "experience"]. None searches all four tables.

    Returns:
        list | None: A ranked list of matching records (each with
        entity_type, entity_id, text, score; possibly empty when nothing
        matches), or None if the search could not run (for example the
        query embedding could not be created).
    """
    if not isinstance(query_text, str) or not query_text.strip():
        print("Semantic search failed: query text must be a non-empty string.")
        return None

    query_vectors = get_embeddings([query_text.strip()])

    if query_vectors is None:
        print("Semantic search failed: could not create query embedding.")
        return None

    query_vector = query_vectors[0]
    model = os.getenv("EMBEDDING_MODEL")

    sql = (
        "SELECT entity_type, entity_id, embed_text, vector "
        "FROM embeddings WHERE model = ?"
    )
    params = [model]

    entity_types = normalize_tables(tables)
    if entity_types:
        placeholders = ", ".join("?" for _ in entity_types)
        sql += f" AND entity_type IN ({placeholders})"
        params.extend(entity_types)

    rows = db.query(sql, tuple(params))

    scored = []

    for row in rows:
        try:
            stored_vector = json.loads(row["vector"])
        except (ValueError, TypeError):
            print("Semantic search: skipping an invalid stored embedding vector.")
            continue

        scored.append(
            {
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "text": row["embed_text"],
                "score": cosine_similarity(query_vector, stored_vector),
            }
        )

    scored.sort(key=lambda result: result["score"], reverse=True)

    # Show the best candidates, accepted or not (useful for the trace and
    # for choosing the cut-off).
    for result in scored[:3]:
        status = "accepted" if result["score"] >= min_score else "rejected"
        print(
            f"[Semantic Search] candidate {result['entity_type']}#{result['entity_id']} "
            f"score={result['score']:.4f} ({status}, cut-off {min_score}) "
            f"text={result['text']}"
        )

    matches = [result for result in scored if result["score"] >= min_score]

    return matches[:limit]


def embeddings_count(db):
    """
    Count the stored embeddings made with the current EMBEDDING_MODEL.

    Returns:
        int: The number of usable embeddings (0 if none).
    """
    model = os.getenv("EMBEDDING_MODEL")
    rows = db.query("SELECT COUNT(*) AS n FROM embeddings WHERE model = ?", (model,))
    return rows[0]["n"] if rows else 0


# Helper functions


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def build_text(*parts):
    return " ".join(part for part in parts if part)


def table_name_to_entity_type(table_name):
    mapping = {
        "institutions": "institution",
        "positions": "position",
        "skills": "skill",
        "experiences": "experience",
    }

    return mapping.get(table_name)


def normalize_tables(tables):
    """
    Turn a table filter into a list of entity types.
    Accepts table names ("skills") or entity types ("skill"); unknown names
    are reported and ignored.
    """
    if not tables:
        return []

    if isinstance(tables, str):
        tables = [tables]

    entity_types = []

    for name in tables:
        entity_type = table_name_to_entity_type(name) or name

        if entity_type not in ENTITY_TYPES:
            print(f"Semantic search: ignoring unknown table filter {name!r}.")
            continue

        if entity_type not in entity_types:
            entity_types.append(entity_type)

    return entity_types