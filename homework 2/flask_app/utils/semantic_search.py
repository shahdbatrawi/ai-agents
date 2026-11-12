
from flask_app.utils.embeddings import (
    DEFAULT_LIMIT,
    MIN_SCORE,
    embeddings_count,
    search_by_meaning,
)


def semantic_search(db, query_text, tables=None):
    """
    Perform semantic search using stored embeddings.

    Args:
        db: The database object.
        query_text (str): The user's search text.
        tables (list | str | None): Optional table filter, e.g. ["skills"].

    Returns:
        list | None: Ranked matching records (an empty list means "nothing
        matched"), or None if the search could not run. None is passed on
        unchanged so that a failure is never mistaken for "no match".
    """
    return search_by_meaning(
        db,
        query_text,
        limit=DEFAULT_LIMIT,
        min_score=MIN_SCORE,
        tables=tables,
    )


def semantic_search_expert(db, query_text, tables=None):
    """
    Run a semantic search and format the answer for the user.

    Three different outcomes, three different messages:
      - the search could not run  -> "temporarily unavailable"
      - no embeddings are stored  -> the index must be (re)built
      - nothing is close enough   -> "Not found"
    """
    results = semantic_search(db, query_text, tables=tables)

    if results is None:
        return (
            "Semantic search is temporarily unavailable because the "
            "embedding service could not be reached."
        )

    if not results:
        if embeddings_count(db) == 0:
            return (
                "Semantic search is not ready: no embeddings are stored "
                "for the current embedding model."
            )

        return "Not found. No matching records were found."

    lines = []

    for result in results:
        score = result["score"]
        text = result["text"]

        print(
            f"[Semantic Search] result {result['entity_type']}#{result['entity_id']} "
            f"score={score:.4f} text={text}"
        )

        lines.append(f"- {text} (score: {score:.2f})")

    return "Here are the closest matches:\n" + "\n".join(lines)