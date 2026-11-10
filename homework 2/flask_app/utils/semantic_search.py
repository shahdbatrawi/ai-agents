import os
from flask_app.utils.embeddings import search_by_meaning


def semantic_search(db, query_text):
    """
    Perform semantic search using stored embeddings.

    Args:
        db: The database object.
        query_text (str): The user's search text.

    Returns:
        list: Ranked matching records, or an empty list if no match.
    """
    results = search_by_meaning(
        db,
        query_text,
        min_score=0.35,
    )

    if results is None:
        return []

    return results


def semantic_search_expert(db, query_text):
    results = semantic_search(db, query_text)

    if results is None:
        return (
            "Semantic search is temporarily unavailable because the "
            "embedding service could not be reached."
        )

    if not results:
        return "No matching records were found."

    lines = []

    for result in results:
        score = result["score"]
        text = result["text"]

        print(f"[Semantic Search] score={score:.4f} text={text}")

        lines.append(f"- {text} (score: {score:.2f})")

    return "Here are the closest matches:\n" + "\n".join(lines)
