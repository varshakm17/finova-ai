"""Unit tests for EmbeddingService."""

import numpy as np
import pytest

from backend.retrieval.embedding_service import EmbeddingService


def test_lazy_initialization() -> None:
    """Verify EmbeddingService does not initialize or download the model upon instantiation."""
    service = EmbeddingService(model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert service._model is None
    meta = service.get_model_metadata()
    assert meta["is_loaded"] is False
    assert meta["dimension"] == 384
    assert meta["device"] == "cpu"


def test_encode_texts_input_validation() -> None:
    """Verify input validation rejects invalid types and empty strings."""
    service = EmbeddingService()

    # Empty list returns empty array of shape (0, 384)
    res = service.encode_texts([])
    assert res.shape == (0, 384)

    # Non-list input raises TypeError
    with pytest.raises(TypeError, match="Expected a list"):
        service.encode_texts("not a list")  # type: ignore[arg-type]

    # Non-string element in list raises TypeError
    with pytest.raises(TypeError, match="is not a string"):
        service.encode_texts(["valid text", 123])  # type: ignore[list-item]

    # Whitespace-only string raises ValueError
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.encode_texts(["valid text", "   \n\t  "])


def test_encode_query_input_validation() -> None:
    """Verify query validation rejects invalid inputs."""
    service = EmbeddingService()

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.encode_query("")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.encode_query("   ")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.encode_query(None)  # type: ignore[arg-type]


def test_encode_with_mock_encoder_fn() -> None:
    """Verify encoding with an injected mock encoder for fast offline testing."""

    def mock_encoder(texts: list[str]) -> np.ndarray:
        # Generate deterministic synthetic vectors
        vectors = []
        for i, text in enumerate(texts):
            # Seed-like vector based on text length
            vec = np.zeros(384, dtype=np.float32)
            vec[i % 384] = float(len(text))
            vec[(i + 1) % 384] = 1.0
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    service = EmbeddingService(
        model_name="mock-model",
        dimension=384,
        encoder_fn=mock_encoder,
    )

    texts = [
        "Apple reports record quarterly revenue of $89.5B.",
        "Supply chain constraints in semiconductors.",
    ]

    embeddings = service.encode_texts(texts)

    assert embeddings.shape == (2, 384)
    assert embeddings.dtype == np.float32

    # Verify unit normalization (L2 norm == 1.0)
    for row in embeddings:
        norm = np.linalg.norm(row)
        assert norm == pytest.approx(1.0, rel=1e-5)

    # Test encode_query
    q_vec = service.encode_query("semiconductor supply chain")
    assert q_vec.shape == (384,)
    assert np.linalg.norm(q_vec) == pytest.approx(1.0, rel=1e-5)


def test_dimension_mismatch_detection() -> None:
    """Verify dimension mismatch in encoder output raises ValueError."""

    def bad_dim_encoder(texts: list[str]) -> np.ndarray:
        # Returns 128D instead of 384D
        return np.ones((len(texts), 128), dtype=np.float32)

    service = EmbeddingService(dimension=384, encoder_fn=bad_dim_encoder)

    with pytest.raises(ValueError, match="does not match expected"):
        service.encode_texts(["Some text"])


def test_load_model_with_mocked_transformer() -> None:
    """Verify load_model correctly instantiates SentenceTransformer and sets eval mode."""
    from unittest.mock import MagicMock, patch

    mock_instance = MagicMock()
    mock_instance.encode.return_value = np.ones((1, 384), dtype=np.float32)

    with patch(
        "sentence_transformers.SentenceTransformer", return_value=mock_instance
    ) as mock_cls:
        service = EmbeddingService(model_name="test-model", dimension=384)
        service.load_model()
        mock_cls.assert_called_once_with("test-model", device="cpu")
        mock_instance.eval.assert_called_once()
        assert service._model is mock_instance

        # Test encoding through the mocked SentenceTransformer
        res = service.encode_texts(["Sample text"])
        assert res.shape == (1, 384)
        assert np.linalg.norm(res[0]) == pytest.approx(1.0, rel=1e-5)


def test_load_model_failure_raises_runtime_error() -> None:
    """Verify load_model raises RuntimeError if SentenceTransformer instantiation throws."""
    from unittest.mock import patch

    with patch(
        "sentence_transformers.SentenceTransformer",
        side_effect=Exception("Model weight missing"),
    ):
        service = EmbeddingService(model_name="invalid-model")
        with pytest.raises(
            RuntimeError, match="Failed to load sentence embedding model"
        ):
            service.load_model()
