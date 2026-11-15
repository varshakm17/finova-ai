"""Optional Cross-Encoder Reranking Layer for Finova AI.

Provides a second-stage reranker that evaluates query-candidate pairs using
a lightweight pretrained cross-encoder (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2)
running exclusively on CPU. Preserves original retrieval ranks and provenance.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from backend.retrieval.retrieval_models import (
    HybridSearchResult,
    RerankedSearchResult,
    RerankerStatusResponse,
)
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("reranker")


class CrossEncoderProtocol(Protocol):
    """Protocol defining the interface expected of a cross-encoder model."""

    def predict(
        self,
        sentences: list[tuple[str, str]],
        batch_size: int = 16,
        show_progress_bar: bool = False,
    ) -> Any:
        """Score pairs of query and document text."""
        ...


class CrossEncoderReranker:
    """CPU-compatible cross-encoder reranking service with lazy loading.

    Scores candidate chunks against the input query to produce a refined
    relevance ranking while retaining full statutory provenance and original ranks.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model: CrossEncoderProtocol | None = None,
    ) -> None:
        """Initialize reranker service.

        Args:
            settings: Optional application settings.
            model: Optional pre-initialized cross-encoder model (injected for testing).
        """
        self.settings = settings or get_settings()
        self._model: CrossEncoderProtocol | None = model
        self._initialized: bool = model is not None
        self._is_available: bool = model is not None or self.settings.RERANKER_ENABLED
        self._init_error: str | None = None
        self._benchmarked: bool = False
        self._last_benchmark_latency_ms: float | None = None

    @property
    def is_enabled(self) -> bool:
        """Return whether reranker is enabled in settings."""
        return self.settings.RERANKER_ENABLED

    @property
    def is_initialized(self) -> bool:
        """Return whether cross-encoder model weights are loaded in memory."""
        return self._initialized

    @property
    def is_available(self) -> bool:
        """Return whether reranker is ready to execute scoring."""
        return self._is_available and (self._initialized or self.is_enabled)

    def _load_model(self) -> CrossEncoderProtocol | None:
        """Lazily initialize and load the cross-encoder model on CPU."""
        if self._model is not None:
            return self._model

        if not self.settings.RERANKER_ENABLED:
            logger.info("Reranker is disabled by configuration.")
            self._is_available = False
            return None

        try:
            logger.info(
                "Loading cross-encoder model '%s' on device '%s'...",
                self.settings.RERANKER_MODEL_NAME,
                self.settings.RERANKER_DEVICE,
            )
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                model_name=self.settings.RERANKER_MODEL_NAME,
                device=self.settings.RERANKER_DEVICE,
            )
            self._initialized = True
            self._is_available = True
            logger.info("Cross-encoder model successfully initialized.")
            return self._model
        except Exception as exc:
            self._init_error = str(exc)
            self._initialized = False
            self._is_available = False
            logger.warning(
                "Failed to initialize cross-encoder model '%s': %s. "
                "Retriever will fall back to original ranking without reranking.",
                self.settings.RERANKER_MODEL_NAME,
                exc,
            )
            return None

    def rerank(
        self,
        query: str,
        candidates: list[HybridSearchResult | dict[str, Any]],
        top_k: int | None = None,
        candidate_count: int | None = None,
    ) -> tuple[list[RerankedSearchResult], dict[str, Any]]:
        """Rerank candidates using cross-encoder scoring.

        Args:
            query: Input natural-language search query.
            candidates: List of candidate chunks (HybridSearchResult or dicts).
            top_k: Optional final cutoff count. If None, uses len(candidates).
            candidate_count: Optional max candidates to evaluate with model.

        Returns:
            Tuple of (reranked_results, metadata_dict).
        """
        if not candidates:
            return [], {
                "reranker_applied": False,
                "status": "empty_candidates",
                "duration_ms": 0.0,
                "candidates_in": 0,
                "candidates_out": 0,
            }

        k_target = top_k if top_k is not None else len(candidates)
        pool_size = candidate_count or self.settings.RERANKER_CANDIDATE_COUNT
        candidate_pool = candidates[:pool_size]

        # Check if reranking is enabled and model available
        if not self.settings.RERANKER_ENABLED:
            logger.debug("Reranking disabled. Returning candidates in original order.")
            results = self._fallback_results(candidate_pool, k_target)
            return results, {
                "reranker_applied": False,
                "status": "disabled_by_config",
                "duration_ms": 0.0,
                "candidates_in": len(candidate_pool),
                "candidates_out": len(results),
            }

        model = self._load_model()
        if model is None:
            logger.debug(
                "Reranker model unavailable. Falling back to original ranking."
            )
            results = self._fallback_results(candidate_pool, k_target)
            return results, {
                "reranker_applied": False,
                "status": "model_unavailable",
                "error": self._init_error,
                "duration_ms": 0.0,
                "candidates_in": len(candidate_pool),
                "candidates_out": len(results),
            }

        # Build query-document pairs
        pairs: list[tuple[str, str]] = []
        for cand in candidate_pool:
            text = (
                cand.chunk_text
                if isinstance(cand, HybridSearchResult)
                else cand.get("chunk_text", "")
            )
            pairs.append((query, text))

        start_time = time.perf_counter()
        try:
            scores = model.predict(
                pairs,
                batch_size=self.settings.RERANKER_BATCH_SIZE,
                show_progress_bar=False,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self._last_benchmark_latency_ms = elapsed_ms
            self._benchmarked = True
        except Exception as exc:
            logger.warning("Error during cross-encoder prediction: %s", exc)
            results = self._fallback_results(candidate_pool, k_target)
            return results, {
                "reranker_applied": False,
                "status": "prediction_error",
                "error": str(exc),
                "duration_ms": 0.0,
                "candidates_in": len(candidate_pool),
                "candidates_out": len(results),
            }

        # Pair candidates with their reranker score and original rank
        scored_candidates: list[tuple[float, int, Any]] = []
        for orig_idx, (cand, score) in enumerate(
            zip(candidate_pool, scores, strict=False)
        ):
            scored_candidates.append((float(score), orig_idx + 1, cand))

        # Sort descending by cross-encoder score; tie-break on original rank
        scored_candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)

        # Slice to requested top_k
        final_pool = scored_candidates[:k_target]
        reranked_results: list[RerankedSearchResult] = []

        for new_rank, (score, orig_rank, cand) in enumerate(final_pool, start=1):
            if isinstance(cand, HybridSearchResult):
                reranked_results.append(
                    RerankedSearchResult(
                        chunk_id=cand.chunk_id,
                        ticker=cand.ticker,
                        company_name=cand.company_name,
                        cik=cand.cik,
                        filing_type=cand.filing_type,
                        filing_date=cand.filing_date,
                        report_date=cand.report_date,
                        accession_number=cand.accession_number,
                        section_identifier=cand.section_identifier,
                        section_title=cand.section_title,
                        chunk_text=cand.chunk_text,
                        source_url=cand.source_url,
                        original_rank=orig_rank,
                        rerank_rank=new_rank,
                        rerank_score=score,
                        original_dense_rank=cand.dense_rank,
                        original_dense_score=cand.dense_score,
                        original_sparse_rank=cand.sparse_rank,
                        original_bm25_score=cand.bm25_score,
                        original_rrf_score=cand.rrf_score,
                        retrieval_sources=cand.retrieval_sources,
                    )
                )
            else:
                reranked_results.append(
                    RerankedSearchResult(
                        chunk_id=cand.get("chunk_id", ""),
                        ticker=cand.get("ticker", ""),
                        company_name=cand.get("company_name", ""),
                        cik=cand.get("cik", ""),
                        filing_type=cand.get("filing_type", ""),
                        filing_date=cand.get("filing_date", ""),
                        report_date=cand.get("report_date"),
                        accession_number=cand.get("accession_number", ""),
                        section_identifier=cand.get("section_identifier", ""),
                        section_title=cand.get("section_title", ""),
                        chunk_text=cand.get("chunk_text", ""),
                        source_url=cand.get("source_url", ""),
                        original_rank=orig_rank,
                        rerank_rank=new_rank,
                        rerank_score=score,
                        original_dense_rank=cand.get("dense_rank"),
                        original_dense_score=cand.get("dense_score"),
                        original_sparse_rank=cand.get("sparse_rank"),
                        original_bm25_score=cand.get("bm25_score"),
                        original_rrf_score=cand.get("rrf_score"),
                        retrieval_sources=cand.get("retrieval_sources", ["hybrid"]),
                    )
                )

        metadata = {
            "reranker_applied": True,
            "status": "success",
            "model_name": self.settings.RERANKER_MODEL_NAME,
            "device": self.settings.RERANKER_DEVICE,
            "duration_ms": elapsed_ms,
            "candidates_in": len(candidate_pool),
            "candidates_out": len(reranked_results),
            "batch_size": self.settings.RERANKER_BATCH_SIZE,
        }
        return reranked_results, metadata

    def _fallback_results(
        self,
        candidates: list[HybridSearchResult | dict[str, Any]],
        top_k: int,
    ) -> list[RerankedSearchResult]:
        """Convert candidates to RerankedSearchResult preserving original ranking."""
        results: list[RerankedSearchResult] = []
        for idx, cand in enumerate(candidates[:top_k], start=1):
            if isinstance(cand, HybridSearchResult):
                results.append(
                    RerankedSearchResult(
                        chunk_id=cand.chunk_id,
                        ticker=cand.ticker,
                        company_name=cand.company_name,
                        cik=cand.cik,
                        filing_type=cand.filing_type,
                        filing_date=cand.filing_date,
                        report_date=cand.report_date,
                        accession_number=cand.accession_number,
                        section_identifier=cand.section_identifier,
                        section_title=cand.section_title,
                        chunk_text=cand.chunk_text,
                        source_url=cand.source_url,
                        original_rank=idx,
                        rerank_rank=idx,
                        rerank_score=cand.rrf_score,
                        original_dense_rank=cand.dense_rank,
                        original_dense_score=cand.dense_score,
                        original_sparse_rank=cand.sparse_rank,
                        original_bm25_score=cand.bm25_score,
                        original_rrf_score=cand.rrf_score,
                        retrieval_sources=cand.retrieval_sources,
                    )
                )
            else:
                results.append(
                    RerankedSearchResult(
                        chunk_id=cand.get("chunk_id", ""),
                        ticker=cand.get("ticker", ""),
                        company_name=cand.get("company_name", ""),
                        cik=cand.get("cik", ""),
                        filing_type=cand.get("filing_type", ""),
                        filing_date=cand.get("filing_date", ""),
                        report_date=cand.get("report_date"),
                        accession_number=cand.get("accession_number", ""),
                        section_identifier=cand.get("section_identifier", ""),
                        section_title=cand.get("section_title", ""),
                        chunk_text=cand.get("chunk_text", ""),
                        source_url=cand.get("source_url", ""),
                        original_rank=idx,
                        rerank_rank=idx,
                        rerank_score=cand.get("rrf_score", 0.0),
                        original_dense_rank=cand.get("dense_rank"),
                        original_dense_score=cand.get("dense_score"),
                        original_sparse_rank=cand.get("sparse_rank"),
                        original_bm25_score=cand.get("bm25_score"),
                        original_rrf_score=cand.get("rrf_score"),
                        retrieval_sources=cand.get("retrieval_sources", ["hybrid"]),
                    )
                )
        return results

    def get_status(self) -> RerankerStatusResponse:
        """Return structured status of reranker configuration and model initialization."""
        msg: str | None = None
        if not self.settings.RERANKER_ENABLED:
            msg = "Reranking disabled in configuration."
        elif self._init_error:
            msg = f"Model initialization failed: {self._init_error}"
        elif self._initialized:
            msg = "Cross-encoder loaded and ready for scoring."
        else:
            msg = "Reranker enabled; model weights will load lazily on first query."

        return RerankerStatusResponse(
            enabled=self.settings.RERANKER_ENABLED,
            model_name=self.settings.RERANKER_MODEL_NAME,
            device=self.settings.RERANKER_DEVICE,
            batch_size=self.settings.RERANKER_BATCH_SIZE,
            candidate_count=self.settings.RERANKER_CANDIDATE_COUNT,
            initialized=self._initialized,
            is_available=self.is_available,
            benchmarked=self._benchmarked,
            last_benchmark_latency_ms=self._last_benchmark_latency_ms,
            message=msg,
        )

    def benchmark_latency(
        self,
        query: str = "What are the company's primary supply chain risks?",
        sample_chunks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a CPU latency benchmark using synthetic or provided texts.

        Does not download or initialize the model if reranker is disabled.
        """
        if not self.settings.RERANKER_ENABLED:
            return {
                "benchmarked": False,
                "error": "Reranker is disabled in settings.",
                "latency_ms": None,
            }

        model = self._load_model()
        if model is None:
            return {
                "benchmarked": False,
                "error": f"Model could not be loaded: {self._init_error}",
                "latency_ms": None,
            }

        texts = sample_chunks or [
            "Supply chain disruptions may adversely affect operational output and component costs.",
            "We rely on single-source suppliers for several key hardware components and manufacturing.",
            "Operating margins increased by 150 basis points due to favorable product mix.",
            "Total net debt decreased following debt repayment and commercial paper settlement.",
            "Quantitative disclosures concerning interest rate swaps and foreign currency risk.",
        ]

        pairs = [(query, t) for t in texts]
        start = time.perf_counter()
        _ = model.predict(pairs, batch_size=len(pairs), show_progress_bar=False)
        duration_ms = (time.perf_counter() - start) * 1000.0

        self._benchmarked = True
        self._last_benchmark_latency_ms = duration_ms

        return {
            "benchmarked": True,
            "pairs_evaluated": len(pairs),
            "total_latency_ms": round(duration_ms, 2),
            "latency_per_pair_ms": round(duration_ms / len(pairs), 2),
            "device": self.settings.RERANKER_DEVICE,
            "model_name": self.settings.RERANKER_MODEL_NAME,
        }
