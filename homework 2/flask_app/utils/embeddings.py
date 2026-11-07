"""embeddings.py - calls the embedding model and validates what comes back."""
import math
import os

import requests

EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


class EmbeddingError(Exception):
    """Raised whenever an embedding could not be produced or looks invalid."""


def embed_texts(texts):
    """Return one validated vector per text, or raise EmbeddingError."""
    if not texts:
        return []
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("EMBEDDING_MODEL")
    if not api_key:
        raise EmbeddingError("OPENROUTER_API_KEY is missing in .env")
    if not model:
        raise EmbeddingError("EMBEDDING_MODEL is missing in .env")

    try:
        resp = requests.post(
            EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": texts},
            timeout=30,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as error:
        raise EmbeddingError(f"Embedding request failed ({type(error).__name__})") from error

    if resp.status_code != 200 or not isinstance(data, dict) or "data" not in data:
        detail = f"HTTP {resp.status_code}"
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            detail = data["error"].get("message", detail)
        raise EmbeddingError(f"Embedding API error: {detail}")

    items = sorted(data["data"], key=lambda item: item.get("index", 0))
    if len(items) != len(texts):
        raise EmbeddingError("Embedding API returned the wrong number of vectors")

    vectors = []
    for item in items:
        vec = item.get("embedding")
        valid = (
            isinstance(vec, list)
            and len(vec) > 0
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in vec)
            and any(v != 0 for v in vec)
        )
        if not valid:
            raise EmbeddingError("Embedding API returned an empty or all-zero vector")
        vectors.append(vec)
    return vectors


def cosine_similarity(a, b):
    """Cosine similarity of two equal-length vectors (plain Python)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)