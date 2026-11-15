"""Modular Vector Store Engine for Financial Document Chunks.

Supports persistent exact cosine-similarity search using NumPy as the robust
default engine, with optional FAISS CPU backend support.
Provides vector persistence, dimension validation, duplicate prevention,
incremental updates, deletion, and index rebuilding.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from backend.utils.logger import get_logger

logger = get_logger("vector_store")

# Attempt optional FAISS import
try:
    import faiss  # type: ignore[import-untyped]

    FAISS_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    faiss = None
    FAISS_AVAILABLE = False


def normalize_vector(v: np.ndarray) -> np.ndarray:
    """Normalize a vector or 2D array of vectors to unit L2 norm for cosine similarity."""
    if v.ndim == 1:
        norm = np.linalg.norm(v)
        if norm > 0:
            return (v / norm).astype(np.float32)
        return v.astype(np.float32)
    elif v.ndim == 2:
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        # Avoid division by zero for zero vectors
        norms = np.where(norms == 0, 1.0, norms)
        return (v / norms).astype(np.float32)
    else:
        raise ValueError(f"Vector array must be 1D or 2D, got shape {v.shape}")


class BaseVectorStore(ABC):
    """Abstract base class defining vector storage and similarity retrieval operations."""

    def __init__(
        self, dimension: int = 384, index_dir: Path | str | None = None
    ) -> None:
        self.dimension = dimension
        self.index_dir = Path(index_dir) if index_dir else Path("datasets/indexes")
        self.index_dir.mkdir(parents=True, exist_ok=True)

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Name of the vector indexing backend engine."""

    @abstractmethod
    def add_vectors(self, vector_ids: list[str], vectors: np.ndarray) -> None:
        """Add or update vectors with associated unique string identifiers."""

    @abstractmethod
    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> list[tuple[str, float]]:
        """Find the top-k most similar vectors to the query vector."""

    @abstractmethod
    def remove_vectors(self, vector_ids: list[str]) -> int:
        """Remove vectors from the index by vector ID."""

    @abstractmethod
    def save(self, directory: Path | str | None = None) -> None:
        """Persist index structures and vector ID mappings to disk."""

    @abstractmethod
    def load(self, directory: Path | str | None = None) -> bool:
        """Load index structures from disk."""

    @abstractmethod
    def get_index_stats(self) -> dict[str, Any]:
        """Return diagnostic metrics about the active vector index."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all in-memory vectors and mapping structures."""

    def rebuild(self, vector_ids: list[str], vectors: np.ndarray) -> None:
        """Reconstruct index from a complete set of vectors and persist."""
        self.clear()
        if vector_ids and len(vectors) > 0:
            self.add_vectors(vector_ids, vectors)
        self.save()


class NumpyVectorStore(BaseVectorStore):
    """Clean, high-performance exact cosine-similarity vector store using NumPy."""

    def __init__(
        self, dimension: int = 384, index_dir: Path | str | None = None
    ) -> None:
        super().__init__(dimension=dimension, index_dir=index_dir)
        self._vector_ids: list[str] = []
        self._id_to_idx: dict[str, int] = {}
        self._vectors: np.ndarray | None = None

    @property
    def backend_name(self) -> str:
        return "numpy"

    def add_vectors(self, vector_ids: list[str], vectors: np.ndarray) -> None:
        """Add or update vectors in the index."""
        if not vector_ids:
            return

        if len(vector_ids) != len(vectors):
            raise ValueError(
                f"Mismatch: {len(vector_ids)} vector IDs provided for {len(vectors)} vectors"
            )

        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Vectors shape {vectors.shape} does not match expected dimension {self.dimension}"
            )

        # Check for duplicates within the input batch
        if len(vector_ids) != len(set(vector_ids)):
            raise ValueError("Duplicate vector IDs found within the input batch")

        normed_vectors = normalize_vector(vectors)

        # If index is empty, initialize arrays directly
        if self._vectors is None or len(self._vector_ids) == 0:
            self._vector_ids = list(vector_ids)
            self._id_to_idx = {vid: i for i, vid in enumerate(self._vector_ids)}
            self._vectors = normed_vectors.copy()
            return

        # Handle updates and additions
        existing_updates: list[tuple[int, np.ndarray]] = []
        new_ids: list[str] = []
        new_vecs: list[np.ndarray] = []

        for vid, vec in zip(vector_ids, normed_vectors, strict=False):
            if vid in self._id_to_idx:
                existing_updates.append((self._id_to_idx[vid], vec))
            else:
                new_ids.append(vid)
                new_vecs.append(vec)

        # Apply in-place replacements for existing IDs
        for idx, vec in existing_updates:
            self._vectors[idx] = vec

        # Append novel vectors
        if new_ids:
            start_idx = len(self._vector_ids)
            self._vectors = np.vstack(
                [self._vectors, np.array(new_vecs, dtype=np.float32)]
            )
            for i, vid in enumerate(new_ids):
                self._id_to_idx[vid] = start_idx + i
            self._vector_ids.extend(new_ids)

        logger.debug(
            "Added/updated %d vectors. Total index size: %d",
            len(vector_ids),
            len(self._vector_ids),
        )

    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> list[tuple[str, float]]:
        """Search nearest vectors using cosine similarity (inner product of unit vectors)."""
        if self._vectors is None or len(self._vector_ids) == 0 or top_k <= 0:
            return []

        q = np.asarray(query_vector, dtype=np.float32)
        if q.ndim == 2:
            if q.shape[0] != 1 or q.shape[1] != self.dimension:
                raise ValueError(
                    f"Query vector shape {q.shape} invalid; expected ({self.dimension},)"
                )
            q = q.squeeze(0)
        elif q.ndim == 1:
            if len(q) != self.dimension:
                raise ValueError(
                    f"Query vector dimension {len(q)} != index dimension {self.dimension}"
                )
        else:
            raise ValueError(f"Invalid query vector dimensions: {q.ndim}")

        norm_q = normalize_vector(q)

        # Exact cosine similarity via matrix-vector multiplication
        scores = np.dot(self._vectors, norm_q)

        # Find top-k indices
        k = min(top_k, len(self._vector_ids))
        if k == len(self._vector_ids):
            top_indices = np.argsort(-scores)
        else:
            # Use argpartition for O(N) selection followed by sort of top-k
            partition_idx = np.argpartition(-scores, k)[:k]
            top_indices = partition_idx[np.argsort(-scores[partition_idx])]

        results: list[tuple[str, float]] = []
        for idx in top_indices:
            vid = self._vector_ids[idx]
            sim = float(scores[idx])
            results.append((vid, sim))

        return results

    def remove_vectors(self, vector_ids: list[str]) -> int:
        """Remove vectors by ID and repack the array."""
        if not vector_ids or self._vectors is None or len(self._vector_ids) == 0:
            return 0

        target_set = set(vector_ids)
        keep_indices: list[int] = []
        new_ids: list[str] = []

        for i, vid in enumerate(self._vector_ids):
            if vid not in target_set:
                keep_indices.append(i)
                new_ids.append(vid)

        removed_count = len(self._vector_ids) - len(new_ids)
        if removed_count == 0:
            return 0

        if len(new_ids) == 0:
            self.clear()
            return removed_count

        self._vectors = self._vectors[keep_indices]
        self._vector_ids = new_ids
        self._id_to_idx = {vid: i for i, vid in enumerate(self._vector_ids)}
        return removed_count

    def save(self, directory: Path | str | None = None) -> None:
        """Persist vectors to .npy and mapping to .json."""
        target_dir = Path(directory) if directory else self.index_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        vecs_file = target_dir / "vectors.npy"
        ids_file = target_dir / "vector_ids.json"
        meta_file = target_dir / "index_meta.json"

        if self._vectors is not None and len(self._vector_ids) > 0:
            np.save(vecs_file, self._vectors)
        else:
            np.save(vecs_file, np.empty((0, self.dimension), dtype=np.float32))

        with open(ids_file, "w", encoding="utf-8") as f:
            json.dump(self._vector_ids, f, indent=2)

        metadata = {
            "backend": self.backend_name,
            "dimension": self.dimension,
            "total_vectors": len(self._vector_ids),
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.debug("Persisted %d vectors to %s", len(self._vector_ids), target_dir)

    def load(self, directory: Path | str | None = None) -> bool:
        """Load vector array and ID mapping from disk."""
        target_dir = Path(directory) if directory else self.index_dir
        vecs_file = target_dir / "vectors.npy"
        ids_file = target_dir / "vector_ids.json"

        if not vecs_file.exists() or not ids_file.exists():
            logger.debug("No existing vector store found at %s", target_dir)
            return False

        try:
            with open(ids_file, encoding="utf-8") as f:
                loaded_ids = json.load(f)

            loaded_vecs = np.load(vecs_file)

            if len(loaded_ids) != len(loaded_vecs):
                logger.warning(
                    "Index mismatch: %d IDs != %d vectors in %s",
                    len(loaded_ids),
                    len(loaded_vecs),
                    target_dir,
                )
                return False

            if loaded_vecs.shape[0] > 0 and loaded_vecs.shape[1] != self.dimension:
                logger.warning(
                    "Dimension mismatch: loaded %d != expected %d",
                    loaded_vecs.shape[1],
                    self.dimension,
                )
                return False

            self._vector_ids = list(loaded_ids)
            self._id_to_idx = {vid: i for i, vid in enumerate(self._vector_ids)}
            self._vectors = loaded_vecs.astype(np.float32)
            logger.info("Loaded %d vectors from %s", len(self._vector_ids), target_dir)
            return True

        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.error("Failed to load vector store from %s: %s", target_dir, exc)
            return False

    def get_index_stats(self) -> dict[str, Any]:
        """Return diagnostic metrics."""
        return {
            "backend": self.backend_name,
            "total_vectors": len(self._vector_ids),
            "dimension": self.dimension,
            "index_dir": str(self.index_dir),
            "is_empty": len(self._vector_ids) == 0,
        }

    def clear(self) -> None:
        """Reset index in memory."""
        self._vector_ids = []
        self._id_to_idx = {}
        self._vectors = None


class FaissVectorStore(BaseVectorStore):
    """FAISS-powered vector store using IndexFlatIP (Inner Product) for normalized vectors."""

    def __init__(
        self, dimension: int = 384, index_dir: Path | str | None = None
    ) -> None:
        if not FAISS_AVAILABLE:
            raise ImportError(
                "faiss is not installed or available in this Python environment. "
                "Use NumpyVectorStore as the reliable CPU backend."
            )
        super().__init__(dimension=dimension, index_dir=index_dir)
        self._vector_ids: list[str] = []
        self._id_to_idx: dict[str, int] = {}
        self._index = faiss.IndexFlatIP(self.dimension)

    @property
    def backend_name(self) -> str:
        return "faiss"

    def add_vectors(self, vector_ids: list[str], vectors: np.ndarray) -> None:
        """Add vectors to FAISS index."""
        if not vector_ids:
            return

        if len(vector_ids) != len(vectors):
            raise ValueError(
                f"Mismatch: {len(vector_ids)} vector IDs provided for {len(vectors)} vectors"
            )

        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Vectors shape {vectors.shape} does not match expected dimension {self.dimension}"
            )

        normed = normalize_vector(vectors)
        self._index.add(normed)
        start_idx = len(self._vector_ids)
        for i, vid in enumerate(vector_ids):
            self._id_to_idx[vid] = start_idx + i
        self._vector_ids.extend(vector_ids)

    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> list[tuple[str, float]]:
        """Search FAISS index using inner product on normalized vectors."""
        if self._index.ntotal == 0 or top_k <= 0:
            return []

        q = np.asarray(query_vector, dtype=np.float32)
        if q.ndim == 1:
            q = q.reshape(1, -1)
        norm_q = normalize_vector(q)

        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(norm_q, k)

        results: list[tuple[str, float]] = []
        for idx, score in zip(indices[0], scores[0], strict=False):
            if 0 <= idx < len(self._vector_ids):
                results.append((self._vector_ids[idx], float(score)))

        return results

    def remove_vectors(self, vector_ids: list[str]) -> int:
        """Remove vectors by rebuilding index without target IDs (IndexFlat does not support ID removal easily)."""
        target_set = set(vector_ids)
        keep_ids: list[str] = []
        keep_vecs: list[np.ndarray] = []

        for i, vid in enumerate(self._vector_ids):
            if vid not in target_set:
                keep_ids.append(vid)
                vec = self._index.reconstruct(i)
                keep_vecs.append(vec)

        removed_count = len(self._vector_ids) - len(keep_ids)
        if removed_count > 0:
            self.clear()
            if keep_ids:
                self.add_vectors(keep_ids, np.array(keep_vecs, dtype=np.float32))
        return removed_count

    def save(self, directory: Path | str | None = None) -> None:
        """Save FAISS index file and vector ID mapping."""
        target_dir = Path(directory) if directory else self.index_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        index_file = target_dir / "index.faiss"
        ids_file = target_dir / "vector_ids.json"

        faiss.write_index(self._index, str(index_file))
        with open(ids_file, "w", encoding="utf-8") as f:
            json.dump(self._vector_ids, f, indent=2)

    def load(self, directory: Path | str | None = None) -> bool:
        """Load FAISS index file and vector ID mapping."""
        target_dir = Path(directory) if directory else self.index_dir
        index_file = target_dir / "index.faiss"
        ids_file = target_dir / "vector_ids.json"

        if not index_file.exists() or not ids_file.exists():
            return False

        try:
            self._index = faiss.read_index(str(index_file))
            with open(ids_file, encoding="utf-8") as f:
                self._vector_ids = json.load(f)
            self._id_to_idx = {vid: i for i, vid in enumerate(self._vector_ids)}
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load FAISS index: %s", exc)
            return False

    def get_index_stats(self) -> dict[str, Any]:
        """Return diagnostic metrics."""
        return {
            "backend": self.backend_name,
            "total_vectors": self._index.ntotal,
            "dimension": self.dimension,
            "index_dir": str(self.index_dir),
            "is_empty": self._index.ntotal == 0,
        }

    def clear(self) -> None:
        """Reset FAISS index."""
        self._index = faiss.IndexFlatIP(self.dimension)
        self._vector_ids = []
        self._id_to_idx = {}


def get_vector_store(
    backend: str = "auto",
    dimension: int = 384,
    index_dir: Path | str | None = None,
) -> BaseVectorStore:
    """Factory creating an initialized vector store backend.

    Args:
        backend: 'auto', 'faiss', or 'numpy'.
        dimension: Embedding vector dimension (default: 384).
        index_dir: Target persistence directory.

    Returns:
        BaseVectorStore: Instantiated vector store backend.
    """
    clean_backend = backend.lower().strip()

    if clean_backend == "faiss":
        if FAISS_AVAILABLE:
            logger.info("Using FAISS CPU vector store backend.")
            store: BaseVectorStore = FaissVectorStore(
                dimension=dimension, index_dir=index_dir
            )
        else:
            logger.warning(
                "FAISS backend requested but faiss is not installed. Falling back to NumpyVectorStore."
            )
            store = NumpyVectorStore(dimension=dimension, index_dir=index_dir)
    elif clean_backend == "numpy":
        logger.info("Using NumPy vector store backend (exact cosine similarity).")
        store = NumpyVectorStore(dimension=dimension, index_dir=index_dir)
    else:  # 'auto'
        if FAISS_AVAILABLE:
            logger.info("Auto-selected FAISS CPU vector store backend.")
            store = FaissVectorStore(dimension=dimension, index_dir=index_dir)
        else:
            logger.info(
                "Auto-selected NumPy vector store backend (exact cosine similarity)."
            )
            store = NumpyVectorStore(dimension=dimension, index_dir=index_dir)

    # Automatically load existing index from disk if present
    store.load()
    return store
