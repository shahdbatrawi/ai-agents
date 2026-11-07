"""Check one real embedding request without touching the database."""

import math
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env")

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_EMBEDDING_MODEL")

    if not api_key or not model:
        raise ValueError(
            "Missing OPENROUTER_API_KEY or "
            "OPENROUTER_EMBEDDING_MODEL in .env."
        )

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": "Michigan State University, Computer Science",
                "encoding_format": "float",
            },
            timeout=45,
        )
    except requests.RequestException:
        raise RuntimeError(
            "Could not reach OpenRouter. Try again."
        ) from None

    print("HTTP status:", response.status_code)

    if not response.ok:
        raise RuntimeError(
            f"Embedding request failed: HTTP {response.status_code}. "
            "Check model availability, permissions, and rate limits."
        )

    try:
        result = response.json()

        if "error" in result:
            raise ValueError("The API returned an error.")

        vector = result["data"][0]["embedding"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError(
            "The API did not return a valid embedding."
        ) from None

    if not isinstance(vector, list) or not vector:
        raise ValueError("Embedding is empty or is not a list.")

    if not all(
        type(value) in (int, float) and math.isfinite(value)
        for value in vector
    ):
        raise ValueError("Embedding contains invalid numbers.")

    if not any(value != 0 for value in vector):
        raise ValueError("Embedding contains only zeros.")

    print("Model:", model)
    print("Vector length:", len(vector))
    print("PASS: Embedding contains valid, nonzero numbers.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print("FAIL:", error)
        raise SystemExit(1)