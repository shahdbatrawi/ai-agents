from flask_app.utils.embeddings import get_embeddings
from dotenv import __main__, load_dotenv


load_dotenv()
def test_embedding_success():
    texts = [
        "Michigan State University",
        "Machine Learning",
        "Public Speaking",
    ]

    vectors = get_embeddings(texts)

    assert vectors is not None
    assert len(vectors) == len(texts)

    for vector in vectors:
        assert isinstance(vector, list)
        assert len(vector) > 0
        assert any(value != 0 for value in vector)

    print("PASS: get_embeddings returned valid vectors.")


def test_embedding_empty_text():
    vectors = get_embeddings(["Michigan State University", "   "])

    assert vectors is None
    print("PASS: empty text was rejected.")


def test_embedding_empty_list():
    vectors = get_embeddings([])

    assert vectors is None
    print("PASS: empty list was rejected.")


def test_embedding_missing_model():
    # This test assumes EMBEDDING_MODEL is not set in the environment.
    import os

    original_model = os.environ.get("EMBEDDING_MODEL")
    os.environ["EMBEDDING_MODEL"] = ""

    vectors = get_embeddings(["Michigan State University"])

    assert vectors is None
    print("PASS: missing model was rejected.")

    if original_model is not None:
        os.environ["EMBEDDING_MODEL"] = original_model


def test_embedding_wrong_model():
    import os

    original_model = os.environ.get("EMBEDDING_MODEL")

    os.environ["EMBEDDING_MODEL"] = "definitely-invalid-model-name"

    vectors = get_embeddings(["Michigan State University"])

    assert vectors is None

    print("PASS: invalid model caused a clear embedding failure.")

    if original_model is not None:
        os.environ["EMBEDDING_MODEL"] = original_model
        
if __name__ == "__main__":
    test_embedding_success()
    test_embedding_empty_text()
    test_embedding_empty_list()
    test_embedding_missing_model()
    test_embedding_wrong_model()