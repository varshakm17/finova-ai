"""Embedding Service for Semantic Representation of Financial Document Chunks.

Encapsulates sentence-transformers model loading, batch encoding, CPU inference,
and vector L2 normalization. Enforces lazy initialization so importing the service
or running tests never initiates unintended model downloads.
"""

from collections.abc import Callable
from typing import Any

import numpy as np

from backend.retrieval.vector_store import normalize_vector
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("embedding_service")


class EmbeddingService:
    """Manages local CPU sentence embedding generation and normalization."""

    def __init__(
        self,
        settings: Settings | None = None,
        model_name: str | None = None,
        device: str | None = None,
        batch_size: int | None = None,
        dimension: int | None = None,
        encoder_fn: Callable[[list[str]], np.ndarray] | None = None,
    ) -> None:
        """Initialize embedding service with lazy model loading.

        Args:
            settings: Optional application settings.
            model_name: Name of sentence transformer model.
            device: Compute device ('cpu' explicitly by default).
            batch_size: Default batch size for text encoding.
            dimension: Expected vector dimension (default: 384 for all-MiniLM-L6-v2).
            encoder_fn: Optional mock encoder callable for offline unit testing.
        """
        cfg = settings or get_settings()
        self.model_name = model_name or cfg.EMBEDDING_MODEL_NAME
        self.device = (device or cfg.EMBEDDING_DEVICE).lower().strip()
        self.batch_size = batch_size or cfg.EMBEDDING_BATCH_SIZE
        self.dimension = dimension or cfg.EMBEDDING_DIMENSION
        self._encoder_fn = encoder_fn

        # Internal model reference (lazy-loaded on first call to encode)
        self._model: Any = None

    def load_model(self) -> None:
        """Instantiate and prepare the pretrained sentence embedding model on CPU."""
        if self._encoder_fn is not None:
            logger.debug("Using injected mock encoder function; skipping model load.")
            return

        if self._model is not None:
            return

        logger.info(
            "Loading embedding model '%s' on device '%s' (batch_size=%d)...",
            self.model_name,
            self.device,
            self.batch_size,
        )

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
        except (ImportError, ModuleNotFoundError) as exc:
            raise ImportError(
                "sentence-transformers is required for local embedding generation. "
                "Ensure sentence-transformers is installed in the virtual environment."
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_name, device=self.device)
            # Ensure model is in evaluation/inference mode
            if hasattr(self._model, "eval"):
                self._model.eval()
            logger.info(
                "Embedding model '%s' initialized successfully. Dimension: %d, Device: %s",
                self.model_name,
                self.dimension,
                self.device,
            )
        except Exception as exc:
            logger.error(
                "Failed to load embedding model '%s': %s", self.model_name, exc
            )
            raise RuntimeError(
                f"Failed to load sentence embedding model '{self.model_name}': {exc}"
            ) from exc

    def encode_texts(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> np.ndarray:
        """Generate normalized dense embeddings for a list of texts.

        Args:
            texts: List of input strings to encode.
            batch_size: Optional batch size override.

        Returns:
            np.ndarray: Array of shape (len(texts), dimension) with float32 values.

        Raises:
            TypeError: If input is not a list.
            ValueError: If texts contains empty or whitespace-only elements.
        """
        if not isinstance(texts, list):
            raise TypeError(
                f"Expected a list of strings to encode, got {type(texts).__name__}"
            )

        if len(texts) == 0:
            return np.empty((0, self.dimension), dtype=np.float32)

        # Validate that all elements are non-empty strings
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise TypeError(
                    f"Item at index {i} is not a string: {type(text).__name__}"
                )
            if not text.strip():
                raise ValueError(
                    f"Item at index {i} is empty or whitespace-only; cannot encode."
                )

        # Ensure model is loaded
        if self._model is None and self._encoder_fn is None:
            self.load_model()

        # Generate raw embeddings via injected mock encoder or sentence_transformers
        if self._encoder_fn is not None:
            raw = self._encoder_fn(texts)
            arr = np.asarray(raw, dtype=np.float32)
        else:
            eff_batch = batch_size or self.batch_size
            raw = self._model.encode(
                texts,
                batch_size=eff_batch,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            arr = np.asarray(raw, dtype=np.float32)

        # Ensure correct shape and dimension
        if arr.ndim != 2 or arr.shape[1] != self.dimension:
            raise ValueError(
                f"Generated embedding dimension {arr.shape} does not match expected (N, {self.dimension})"
            )

        # Final normalization check
        normed = normalize_vector(arr)
        return normed

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single natural-language search query into a 1D unit vector.

        Args:
            query: Query string.

        Returns:
            np.ndarray: 1D normalized float32 vector of shape (dimension,).
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query string cannot be empty or whitespace-only.")

        vec_2d = self.encode_texts([query])
        return vec_2d[0]

    def get_embedding_dimension(self) -> int:
        """Return the vector dimensionality of this embedding service."""
        return self.dimension

    def get_model_metadata(self) -> dict[str, Any]:
        """Return operational metadata about the configured embedding model."""
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "device": self.device,
            "batch_size": self.batch_size,
            "is_loaded": self._model is not None or self._encoder_fn is not None,
        }
