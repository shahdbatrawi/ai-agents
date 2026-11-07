"""Semantic retrieval and a dependent institution lookup."""

import math
import os

from flask_app.utils.semantic_search import SemanticSearch


def run_semantic_request(db, specification, trace):
    """Run a validated semantic request and return retrieved data."""
    if not isinstance(specification, dict):
        raise ValueError("Semantic request must be an object.")

    required = {"query", "tables", "lookup_experiences"}

    if set(specification) != required:
        raise ValueError("Invalid semantic request fields.")

    query = specification["query"]
    tables = specification["tables"]
    lookup = specification["lookup_experiences"]

    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > 1000
    ):
        raise ValueError("Invalid semantic query.")

    SemanticSearch.validate_tables(tables)

    if type(lookup) is not bool:
        raise ValueError("lookup_experiences must be true or false.")

    if lookup and tables != ["institutions"]:
        raise ValueError(
            "An institution lookup must search institutions only."
        )

    try:
        cutoff = float(os.environ["SEMANTIC_MIN_SCORE"])
    except (KeyError, ValueError):
        raise ValueError(
            "Set SEMANTIC_MIN_SCORE in .env."
        ) from None

    if not math.isfinite(cutoff) or not -1 <= cutoff <= 1:
        raise ValueError("Invalid SEMANTIC_MIN_SCORE.")

    search = SemanticSearch(db)

    # Retrieve raw scores so rejected matches are also visible.
    ranked = search.search(
        query,
        tables,
        min_score=-1.0,
        top_k=5,
    )

    trace(
        "semantic_search",
        query=query,
        tables=tables,
        cutoff=cutoff,
        ranked_results=ranked,
        approval="none",
    )

    accepted = [
        result for result in ranked
        if result["score"] >= cutoff
    ]

    if not accepted:
        trace(
            "semantic_outcome",
            outcome="not_found",
            approval="none",
        )
        return {
            "matches": [],
            "experiences": [],
            "outcome": "not_found",
        }

    if not lookup:
        return {
            "matches": accepted,
            "outcome": "found",
        }

    # Step 2 uses the actual ID retrieved by step 1.
    best_match = accepted[0]
    institution_id = best_match["record_id"]

    institutions = db.query(
        "SELECT inst_id, name FROM institutions WHERE inst_id = ?",
        (institution_id,),
    )

    if not institutions:
        raise ValueError(
            "The matched institution changed. Please try again."
        )

    institution = institutions[0]

    experiences = db.query(
        """
        SELECT
            p.position_id,
            p.title,
            p.responsibilities,
            e.experience_id,
            e.name AS experience_name,
            e.description
        FROM positions AS p
        LEFT JOIN experiences AS e
            ON e.position_id = p.position_id
        WHERE p.inst_id = ?
        ORDER BY p.position_id, e.experience_id
        """,
        (institution_id,),
    )

    trace(
        "dependent_read",
        expert="Database Read Expert",
        reason="Use the institution ID resolved by semantic search.",
        resolved_institution=institution,
        source_match=best_match,
        row_count=len(experiences),
        approval="none",
    )

    return {
        "matches": [best_match],
        "institution": institution,
        "experiences": experiences,
        "outcome": "found",
    } 
