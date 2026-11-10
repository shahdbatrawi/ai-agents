from flask import current_app

from flask_app import create_app

# from flask_app.utils.embeddings import get_embedding_records
# from flask_app.utils.embeddings import create_and_store_embeddings
from flask_app.utils.embeddings import search_by_meaning, semantic_search, semantic_search_expert

# def test_get_embedding_records():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         records = get_embedding_records(db)

#         assert isinstance(records, list)
#         assert len(records) > 0

#         allowed_tables = {
#             "institutions",
#             "positions",
#             "skills",
#             "experiences",
#         }

#         for record in records:
#             assert "entity_type" in record
#             assert "id" in record
#             assert "text" in record

#             assert record["entity_type"] in allowed_tables
#             assert isinstance(record["id"], int)
#             assert isinstance(record["text"], str)
#             assert record["text"].strip() != ""
#             assert "None" not in record["text"]

#         print(f"PASS: built {len(records)} embedding records.")

#         for record in records:
#             print(
#                 f"{record['entity_type']} #{record['id']}: {record['text']}"
#             )


# if __name__ == "__main__":
#     test_get_embedding_records()


# def test_create_and_store_embeddings():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         rows = db.query("""
#             SELECT entity_type, entity_id, embed_text, vector, model
#             FROM embeddings
#             """)

#         assert len(rows) > 0

#         for row in rows:
#             assert row["entity_type"] in [
#                 "institution",
#                 "position",
#                 "skill",
#                 "experience",
#             ]
#             assert isinstance(row["entity_id"], int)
#             assert row["embed_text"].strip() != ""
#             assert row["vector"].strip() != ""
#             assert row["model"].strip() != ""

#         print(f"PASS: stored {len(rows)} embeddings.")


# if __name__ == "__main__":
#     test_create_and_store_embeddings()


# def test_search_by_meaning():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         results = search_by_meaning(db, "Find my MSU experience")

#         assert results is not None
#         assert len(results) > 0

#         print("PASS: semantic search returned ranked results.")

#         for result in results:
#             print(
#                 f"{result['entity_type']} #{result['entity_id']} "
#                 f"score={result['score']:.4f}: {result['text']}"
#             )


# if __name__ == "__main__":
#     test_search_by_meaning()



# def test_search_no_match():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         results = search_by_meaning(db, "Find my Harvard experience")

#         assert results is not None

#         print("PASS: semantic search completed for Harvard query.")

#         for result in results:
#             print(
#                 f"{result['entity_type']} #{result['entity_id']} "
#                 f"score={result['score']:.4f}: {result['text']}"
#             )


# if __name__ == "__main__":
#     test_search_no_match()


# def test_search_cutoff():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         msu_results = search_by_meaning(
#             db,
#             "Find my MSU experience",
#             min_score=0.40,
#         )

#         harvard_results = search_by_meaning(
#             db,
#             "Find my Harvard experience",
#             min_score=0.40,
#         )

#         assert msu_results is not None
#         assert len(msu_results) > 0

#         assert harvard_results is not None
#         assert len(harvard_results) == 0

#         print("PASS: MSU matched, Harvard was filtered out.")

#         for result in msu_results:
#             print(
#                 f"{result['entity_type']} #{result['entity_id']} "
#                 f"score={result['score']:.4f}: {result['text']}"
#             )


# if __name__ == "__main__":
#     test_search_cutoff()


# def test_semantic_search():
#     app, socketio = create_app()

#     with app.app_context():
#         db = current_app.db

#         msu_results = semantic_search(db, "Find my MSU experience")
#         harvard_results = semantic_search(db, "Find my Harvard experience")

#         assert len(msu_results) > 0
#         assert len(harvard_results) == 0

#         print("PASS: semantic_search returned MSU results and no Harvard results.")

# if __name__ == "__main__":
#     test_semantic_search()


def test_semantic_search_expert():
    app, socketio = create_app()

    with app.app_context():
        db = current_app.db

        msu_response = semantic_search_expert(
            db,
            "Find my MSU experience",
        )

        harvard_response = semantic_search_expert(
            db,
            "Find my Harvard experience",
        )

        assert "Michigan State University" in msu_response
        assert "No matching records were found." in harvard_response

        print("PASS: semantic search expert returned correct responses.")
        print(msu_response)
        print(harvard_response)


if __name__ == "__main__":
    test_semantic_search_expert()
