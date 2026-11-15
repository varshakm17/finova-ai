"""Unit tests for Vector Store backends (NumPy and FAISS)."""

from pathlib import Path

import numpy as np
import pytest

from backend.retrieval.vector_store import (
    FAISS_AVAILABLE,
    FaissVectorStore,
    NumpyVectorStore,
    get_vector_store,
    normalize_vector,
)


def make_orthogonal_vectors(num_vecs: int, dim: int = 384) -> np.ndarray:
    """Helper generating distinct normalized synthetic vectors."""
    mat = np.zeros((num_vecs, dim), dtype=np.float32)
    for i in range(num_vecs):
        mat[i, i % dim] = 1.0
    return mat


def test_normalize_vector() -> None:
    """Verify vector normalization produces unit length."""
    v1 = np.array([3.0, 4.0], dtype=np.float32)
    v1_norm = normalize_vector(v1)
    assert np.linalg.norm(v1_norm) == pytest.approx(1.0, rel=1e-5)

    v2 = np.array([[3.0, 4.0], [1.0, 1.0]], dtype=np.float32)
    v2_norm = normalize_vector(v2)
    assert np.linalg.norm(v2_norm[0]) == pytest.approx(1.0, rel=1e-5)
    assert np.linalg.norm(v2_norm[1]) == pytest.approx(1.0, rel=1e-5)

    # 3D array raises ValueError
    with pytest.raises(ValueError, match="1D or 2D"):
        normalize_vector(np.ones((2, 2, 2)))


def test_numpy_vector_store_crud(tmp_path: Path) -> None:
    """Verify add, update, search, remove, save, and reload in NumpyVectorStore."""
    store = NumpyVectorStore(dimension=4, index_dir=tmp_path)
    assert store.backend_name == "numpy"
    assert store.get_index_stats()["total_vectors"] == 0

    # 1. Add vectors
    ids = ["vec_1", "vec_2", "vec_3"]
    # vec_1 is along dim 0, vec_2 along dim 1, vec_3 along dim 2
    vecs = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    store.add_vectors(ids, vecs)
    assert store.get_index_stats()["total_vectors"] == 3

    # 2. Search nearest to vec_1
    query = np.array([1.0, 0.1, 0.0, 0.0], dtype=np.float32)
    matches = store.search(query, top_k=2)
    assert len(matches) == 2
    # vec_1 should be highest similarity
    assert matches[0][0] == "vec_1"
    assert matches[0][1] > 0.99
    # vec_2 is second highest (0.1 component)
    assert matches[1][0] == "vec_2"

    # 3. Update vec_1 to point along dim 3
    store.add_vectors(["vec_1"], np.array([[0.0, 0.0, 0.0, 1.0]], dtype=np.float32))
    assert store.get_index_stats()["total_vectors"] == 3
    # Search with original query: vec_1 should now have 0 similarity
    matches_after_update = store.search(query, top_k=2)
    assert matches_after_update[0][0] == "vec_2"

    # 4. Remove vector
    removed = store.remove_vectors(["vec_3"])
    assert removed == 1
    assert store.get_index_stats()["total_vectors"] == 2

    # 5. Save and reload
    store.save()
    reloaded = NumpyVectorStore(dimension=4, index_dir=tmp_path)
    assert reloaded.load() is True
    assert reloaded.get_index_stats()["total_vectors"] == 2
    assert reloaded._vector_ids == ["vec_1", "vec_2"]


def test_numpy_vector_store_validation_errors(tmp_path: Path) -> None:
    """Verify input validation guards against dimension and length mismatches."""
    store = NumpyVectorStore(dimension=4, index_dir=tmp_path)

    # Length mismatch
    with pytest.raises(ValueError, match="Mismatch"):
        store.add_vectors(["a", "b"], np.zeros((3, 4), dtype=np.float32))

    # Dimension mismatch
    with pytest.raises(ValueError, match="does not match expected dimension"):
        store.add_vectors(["a"], np.zeros((1, 8), dtype=np.float32))

    # Duplicate IDs in same batch
    with pytest.raises(ValueError, match="Duplicate vector IDs"):
        store.add_vectors(["dup", "dup"], np.zeros((2, 4), dtype=np.float32))

    # Query vector dimension mismatch
    store.add_vectors(["a"], np.array([[1, 0, 0, 0]], dtype=np.float32))
    with pytest.raises(ValueError, match="dimension"):
        store.search(np.array([1, 0], dtype=np.float32))


def test_faiss_vector_store_if_available(tmp_path: Path) -> None:
    """Verify FaissVectorStore operations when faiss is installed."""
    if not FAISS_AVAILABLE:
        pytest.skip("FAISS is not installed in this environment.")

    store = FaissVectorStore(dimension=4, index_dir=tmp_path)
    assert store.backend_name == "faiss"

    ids = ["f_1", "f_2"]
    vecs = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.add_vectors(ids, vecs)
    assert store.get_index_stats()["total_vectors"] == 2

    # Search
    matches = store.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), top_k=1)
    assert len(matches) == 1
    assert matches[0][0] == "f_1"
    assert matches[0][1] == pytest.approx(1.0, rel=1e-4)

    # Persistence
    store.save()
    reloaded = FaissVectorStore(dimension=4, index_dir=tmp_path)
    assert reloaded.load() is True
    assert reloaded.get_index_stats()["total_vectors"] == 2

    # Remove
    assert store.remove_vectors(["f_1"]) == 1
    assert store.get_index_stats()["total_vectors"] == 1


def test_vector_store_factory(tmp_path: Path) -> None:
    """Verify factory instantiation for different backend preferences."""
    store_numpy = get_vector_store(
        backend="numpy", dimension=16, index_dir=tmp_path / "numpy"
    )
    assert store_numpy.backend_name == "numpy"

    store_auto = get_vector_store(
        backend="auto", dimension=16, index_dir=tmp_path / "auto"
    )
    assert store_auto.backend_name in {"faiss", "numpy"}
