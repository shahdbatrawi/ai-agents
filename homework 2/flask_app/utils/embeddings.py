import json
import os
import math
import requests


def get_embeddings(texts):
    """
    Get the embeddings for a list of texts using the OpenRouter API.

    Args:
        texts (list): A list of input texts to be embedded.

    Returns:
        list: A list of embedding vectors for the input texts.
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

        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            # json={"model": model, "input": ["Michigan State University", "Machine Learning",""]},
            # HTTP status: 400
            # OpenRouter rejects empty input strings with HTTP 400.
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
        list: The embedding vector for the input text.
    """
    vectors = get_embeddings([text])
    return vectors[0] if vectors else None


def get_embedding_records(db):
    """
    Read records from the four searchable tables and prepare the text
    that will later be converted into an embedding.

    Args:
        db: The SQLite database connection.

    Returns:
        list: A list of dictionaries. Each dictionary contains:
            - table: the source table name
            - id: the record ID
            - text: the text that will be embedded
    """

    records = []

    # get instituations records
    instituation_rows = db.query(
        "SELECT inst_id, name, city, state FROM institutions"
    )
    for row in instituation_rows:
        instituation_id = row["inst_id"]
        name = clean_text(row["name"])
        city = clean_text(row["city"])
        state = clean_text(row["state"])
        text = build_text(name, city, state)
        if text:
            records.append(
                {"entity_type": "institutions", "id": instituation_id, "text": text}
            )

    # get positions records
    position_rows = db.query(
        "SELECT p.position_id,p.title,p.responsibilities,i.name FROM positions p "
        "JOIN institutions i ON p.inst_id = i.inst_id"
    )
    for row in position_rows:
        position_id = row["position_id"]
        title = clean_text(row["title"])
        responsibilities = clean_text(row["responsibilities"])
        institution_name = clean_text(row["name"])
        text = build_text(title, responsibilities, institution_name)
        if text:
            records.append({"entity_type": "positions", "id": position_id, "text": text})

    # get skills records
    skill_rows = db.query("SELECT skill_id, name, skill_level FROM skills")
    for row in skill_rows:
        skill_id = row["skill_id"]
        name = clean_text(row["name"])
        text = build_text(name)
        if text:
            records.append({"entity_type": "skills", "id": skill_id, "text": text})

    # get experiences records
    experience_rows = db.query(
        "SELECT e.experience_id, e.name AS experience_name, e.description, p.title, i.name AS institution_name "
        "From experiences e Join positions p ON e.position_id = p.position_id "
        "Join institutions i ON p.inst_id = i.inst_id"
    )
    for row in experience_rows:
        experience_id = row["experience_id"]
        name = clean_text(row["experience_name"])
        description = clean_text(row["description"])
        position_title = clean_text(row["title"])
        institution_name = clean_text(row["institution_name"])
        text = build_text(name, position_title, institution_name, description)
        if text:
            records.append({"entity_type": "experiences", "id": experience_id, "text": text})

    return records



def create_and_store_embeddings(db):
    """
    Create embeddings for all searchable records and store them in SQLite.

    Args:
        db: The database object used by the Flask app.

    Returns:
        bool: True if embeddings were created and stored, False otherwise.
    """
    records = get_embedding_records(db)

    if not records:
        print("Embedding storage failed: no records found.")
        return False

    texts = [record["text"] for record in records]

    vectors = get_embeddings(texts)

    if vectors is None:
        print("Embedding storage failed: could not create embeddings.")
        return False

    if len(vectors) != len(records):
        print("Embedding storage failed: vector count does not match record count.")
        return False

    embedding_model = os.getenv("EMBEDDING_MODEL")

    if not embedding_model:
        print("Embedding storage failed: EMBEDDING_MODEL is missing.")
        return False

    stored_count = 0

    for record, vector in zip(records, vectors):
        entity_type = table_name_to_entity_type(record["entity_type"])

        if entity_type is None:
            print(
                "Embedding storage failed: unknown table "
                f"{record['entity_type']}."
            )
            return False

        vector_json = json.dumps(vector)

        db.query(
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
                vector = excluded.vector
            """,
            (
                entity_type,
                record["id"],
                record["text"],
                vector_json,
                embedding_model,
            ),
        )

        stored_count += 1

    print(f"Stored {stored_count} embeddings.")

    return True



import math


def cosine_similarity(vector_a, vector_b):
    """
    Calculate the cosine similarity between two vectors.

    Args:
        vector_a (list): The first vector.
        vector_b (list): The second vector.

    Returns:
        float: The cosine similarity between the two vectors.
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






def search_by_meaning(db, query_text, limit=5, min_score=0.35):
    """
    Search stored embeddings using cosine similarity.

    Args:
        db: The database object.
        query_text (str): The user's search text.
        limit (int): The maximum number of results to return.
        min_score (float): The minimum similarity score required.

    Returns:
        list | None: A ranked list of matching records, or None if the
        query embedding could not be created.
    """
    if not isinstance(query_text, str) or not query_text.strip():
        print("Semantic search failed: query text must be a non-empty string.")
        return None

    query_vectors = get_embeddings([query_text])

    if query_vectors is None:
        print("Semantic search failed: could not create query embedding.")
        return None

    query_vector = query_vectors[0]

    rows = db.query(
        " SELECT entity_type, entity_id, embed_text, vector FROM embeddings "
    )

    results = []

    for row in rows:
        try:
            stored_vector = json.loads(row["vector"])
        except (ValueError, TypeError):
            print("Semantic search failed: invalid stored embedding vector.")
            continue

        score = cosine_similarity(query_vector, stored_vector)

        if score >= min_score:
            results.append(
                {
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "text": row["embed_text"],
                    "score": score,
                }
            )

    results.sort(key=lambda result: result["score"], reverse=True)

    return results[:limit]




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
