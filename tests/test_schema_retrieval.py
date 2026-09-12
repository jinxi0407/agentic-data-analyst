from app.schema.metadata import cosine_similarity


def test_cosine_similarity_identical():
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) > 0.99
