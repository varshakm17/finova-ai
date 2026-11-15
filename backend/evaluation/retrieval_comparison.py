"""Retrieval Comparison Engine for Finova AI.

Orchestrates fair, reproducible comparative benchmarks evaluating:
1. Dense Semantic Search (all-MiniLM-L6-v2)
2. Sparse Lexical Search (Financial BM25)
3. Hybrid Search with Reciprocal Rank Fusion (RRF)
4. Optional Cross-Encoder Reranked Hybrid Search

Computes performance deltas, rank shifts, and per-query comparisons across
the identical query set and ground-truth relevance annotations.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.data.document_storage import DocumentStorage
from backend.evaluation.retrieval_evaluator import RetrievalEvaluator
from backend.retrieval.bm25_search import BM25SearchService
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import (
    EvaluationQuery,
    MethodComparisonSummary,
    RetrievalComparisonResponse,
    RetrievalEvaluationReport,
)
from backend.retrieval.semantic_search import SemanticSearchService
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("retrieval_comparison")


class RetrievalComparator:
    """Coordinates comparative multi-method information retrieval benchmarks."""

    def __init__(
        self,
        hybrid_search_service: HybridSearchService | None = None,
        semantic_search_service: SemanticSearchService | None = None,
        bm25_search_service: BM25SearchService | None = None,
        reranker: CrossEncoderReranker | None = None,
        document_storage: DocumentStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.semantic_search = semantic_search_service or SemanticSearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.bm25_search = bm25_search_service or BM25SearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.hybrid_search = hybrid_search_service or HybridSearchService(
            semantic_search_service=self.semantic_search,
            bm25_search_service=self.bm25_search,
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.reranker = reranker or CrossEncoderReranker(settings=self.settings)
        self.evaluator = RetrievalEvaluator(settings=self.settings)

    @staticmethod
    def _compute_relative_delta(
        test_val: float,
        baseline_val: float,
    ) -> float:
        """Calculate percentage delta: ((test - baseline) / baseline) * 100.

        If baseline is 0.0, returns absolute difference rounded to 4 decimals.
        """
        if baseline_val > 0.0:
            return round(((test_val - baseline_val) / baseline_val) * 100.0, 2)
        if test_val > 0.0:
            return 100.0
        return 0.0

    def compare_methods(
        self,
        dataset_path: str | Path | None = None,
        queries: list[EvaluationQuery] | None = None,
        top_k: int = 5,
        include_reranking: bool = True,
        ticker_filter: str | None = None,
    ) -> RetrievalComparisonResponse:
        """Execute comparative evaluation across Dense, Sparse, Hybrid, and Reranked search.

        Args:
            dataset_path: Path to evaluation queries JSON.
            queries: Optional pre-loaded query list.
            top_k: Common rank cutoff.
            include_reranking: Whether to evaluate cross-encoder reranking.
            ticker_filter: Optional ticker to filter queries.

        Returns:
            RetrievalComparisonResponse containing all metrics, deltas, and per-query comparisons.
        """
        start_time = time.perf_counter()

        # 1. Load dataset if not passed directly
        if queries is not None:
            active_queries = queries
            dataset_name = "in_memory_queries"
        else:
            resolved_path = (
                Path(dataset_path)
                if dataset_path
                else Path(self.settings.RETRIEVAL_EVALUATION_DATASET)
            )
            dataset_name = resolved_path.name
            active_queries = self.evaluator.load_dataset(resolved_path)

        if ticker_filter:
            norm_ticker = ticker_filter.strip().upper()
            active_queries = [
                q
                for q in active_queries
                if q.ticker and q.ticker.upper() == norm_ticker
            ]

        if not active_queries:
            raise ValueError(
                f"No valid evaluation queries found matching filter '{ticker_filter}'."
            )

        # 2. Define retriever adaptors
        def dense_retriever(
            q: EvaluationQuery,
            fetch_k: int,
        ) -> tuple[list[str], float]:
            t0 = time.perf_counter()
            results = self.semantic_search.search(
                query=q.query,
                ticker=q.ticker,
                filing_type=q.filing_type,
                section_identifier=q.section_identifier,
                top_k=fetch_k,
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            return [r.chunk_id for r in results], lat_ms

        def sparse_retriever(
            q: EvaluationQuery,
            fetch_k: int,
        ) -> tuple[list[str], float]:
            t0 = time.perf_counter()
            results = self.bm25_search.search(
                query=q.query,
                ticker=q.ticker,
                filing_type=q.filing_type,
                section_identifier=q.section_identifier,
                top_k=fetch_k,
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            return [r.chunk_id for r in results], lat_ms

        def hybrid_retriever(
            q: EvaluationQuery,
            fetch_k: int,
        ) -> tuple[list[str], float]:
            t0 = time.perf_counter()
            response = self.hybrid_search.search(
                query=q.query,
                ticker=q.ticker,
                filing_type=q.filing_type,
                section_identifier=q.section_identifier,
                top_k=fetch_k,
                dense_limit=max(fetch_k, self.settings.HYBRID_DENSE_CANDIDATES),
                sparse_limit=max(fetch_k, self.settings.HYBRID_SPARSE_CANDIDATES),
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            return [r.chunk_id for r in response.results], lat_ms

        def reranked_retriever(
            q: EvaluationQuery,
            fetch_k: int,
        ) -> tuple[list[str], float]:
            t0 = time.perf_counter()
            # Fetch candidates from hybrid search
            cand_limit = max(fetch_k, self.settings.RERANKER_CANDIDATE_COUNT)
            hybrid_resp = self.hybrid_search.search(
                query=q.query,
                ticker=q.ticker,
                filing_type=q.filing_type,
                section_identifier=q.section_identifier,
                top_k=cand_limit,
            )
            reranked_res, _ = self.reranker.rerank(
                query=q.query,
                candidates=hybrid_resp.results,
                top_k=fetch_k,
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0
            return [r.chunk_id for r in reranked_res], lat_ms

        # 3. Evaluate each method
        reports: dict[str, RetrievalEvaluationReport] = {}
        reports["dense"] = self.evaluator.evaluate_retriever(
            retriever_fn=dense_retriever,
            queries=active_queries,
            k=top_k,
            dataset_identifier=dataset_name,
            method_name="dense",
        )

        reports["sparse"] = self.evaluator.evaluate_retriever(
            retriever_fn=sparse_retriever,
            queries=active_queries,
            k=top_k,
            dataset_identifier=dataset_name,
            method_name="sparse",
        )

        reports["hybrid"] = self.evaluator.evaluate_retriever(
            retriever_fn=hybrid_retriever,
            queries=active_queries,
            k=top_k,
            dataset_identifier=dataset_name,
            method_name="hybrid",
        )

        evaluate_reranker = include_reranking and self.reranker.is_available
        if evaluate_reranker:
            reports["hybrid_reranked"] = self.evaluator.evaluate_retriever(
                retriever_fn=reranked_retriever,
                queries=active_queries,
                k=top_k,
                dataset_identifier=dataset_name,
                method_name="hybrid_reranked",
            )

        # 4. Build method summaries
        method_summaries: dict[str, MethodComparisonSummary] = {}
        for m_name, rep in reports.items():
            avg_lat = (
                sum(pq.latency_ms for pq in rep.per_query_results)
                / len(rep.per_query_results)
                if rep.per_query_results
                else 0.0
            )
            method_summaries[m_name] = MethodComparisonSummary(
                method=m_name,
                precision_at_k=rep.metrics.precision_at_k,
                recall_at_k=rep.metrics.recall_at_k,
                mrr=rep.metrics.mrr,
                map_score=rep.metrics.map_score,
                ndcg_at_k=rep.metrics.ndcg_at_k,
                coverage=rep.metrics.coverage,
                avg_latency_ms=round(avg_lat, 2),
            )

        # 5. Compute metric deltas of Hybrid vs. Baselines
        hyb = method_summaries["hybrid"]
        den = method_summaries["dense"]
        spa = method_summaries["sparse"]

        delta_vs_dense = {
            "precision_delta_pct": self._compute_relative_delta(
                hyb.precision_at_k, den.precision_at_k
            ),
            "recall_delta_pct": self._compute_relative_delta(
                hyb.recall_at_k, den.recall_at_k
            ),
            "mrr_delta_pct": self._compute_relative_delta(hyb.mrr, den.mrr),
            "map_delta_pct": self._compute_relative_delta(hyb.map_score, den.map_score),
            "ndcg_delta_pct": self._compute_relative_delta(
                hyb.ndcg_at_k, den.ndcg_at_k
            ),
        }

        delta_vs_sparse = {
            "precision_delta_pct": self._compute_relative_delta(
                hyb.precision_at_k, spa.precision_at_k
            ),
            "recall_delta_pct": self._compute_relative_delta(
                hyb.recall_at_k, spa.recall_at_k
            ),
            "mrr_delta_pct": self._compute_relative_delta(hyb.mrr, spa.mrr),
            "map_delta_pct": self._compute_relative_delta(hyb.map_score, spa.map_score),
            "ndcg_delta_pct": self._compute_relative_delta(
                hyb.ndcg_at_k, spa.ndcg_at_k
            ),
        }

        delta_reranked: dict[str, float] | None = None
        if "hybrid_reranked" in method_summaries:
            rr = method_summaries["hybrid_reranked"]
            delta_reranked = {
                "precision_delta_pct": self._compute_relative_delta(
                    rr.precision_at_k, hyb.precision_at_k
                ),
                "recall_delta_pct": self._compute_relative_delta(
                    rr.recall_at_k, hyb.recall_at_k
                ),
                "mrr_delta_pct": self._compute_relative_delta(rr.mrr, hyb.mrr),
                "map_delta_pct": self._compute_relative_delta(
                    rr.map_score, hyb.map_score
                ),
                "ndcg_delta_pct": self._compute_relative_delta(
                    rr.ndcg_at_k, hyb.ndcg_at_k
                ),
            }

        # 6. Build per-query comparison table
        per_query_comparisons: list[dict[str, Any]] = []
        for idx, q in enumerate(active_queries):
            entry: dict[str, Any] = {
                "query_id": q.query_id,
                "query": q.query,
                "ticker": q.ticker,
                "section": q.section_identifier,
                "expected_relevant_count": len(q.relevant_chunk_ids),
                "dense_precision": (
                    reports["dense"].per_query_results[idx].precision_at_k
                    if idx < len(reports["dense"].per_query_results)
                    else 0.0
                ),
                "sparse_precision": (
                    reports["sparse"].per_query_results[idx].precision_at_k
                    if idx < len(reports["sparse"].per_query_results)
                    else 0.0
                ),
                "hybrid_precision": (
                    reports["hybrid"].per_query_results[idx].precision_at_k
                    if idx < len(reports["hybrid"].per_query_results)
                    else 0.0
                ),
                "dense_recall": (
                    reports["dense"].per_query_results[idx].recall_at_k
                    if idx < len(reports["dense"].per_query_results)
                    else 0.0
                ),
                "sparse_recall": (
                    reports["sparse"].per_query_results[idx].recall_at_k
                    if idx < len(reports["sparse"].per_query_results)
                    else 0.0
                ),
                "hybrid_recall": (
                    reports["hybrid"].per_query_results[idx].recall_at_k
                    if idx < len(reports["hybrid"].per_query_results)
                    else 0.0
                ),
                "hybrid_mrr": (
                    reports["hybrid"].per_query_results[idx].reciprocal_rank
                    if idx < len(reports["hybrid"].per_query_results)
                    else 0.0
                ),
                "hybrid_ndcg": (
                    reports["hybrid"].per_query_results[idx].ndcg_at_k
                    if idx < len(reports["hybrid"].per_query_results)
                    else 0.0
                ),
            }
            if "hybrid_reranked" in reports and idx < len(
                reports["hybrid_reranked"].per_query_results
            ):
                entry["reranked_precision"] = (
                    reports["hybrid_reranked"].per_query_results[idx].precision_at_k
                )
                entry["reranked_recall"] = (
                    reports["hybrid_reranked"].per_query_results[idx].recall_at_k
                )
                entry["reranked_ndcg"] = (
                    reports["hybrid_reranked"].per_query_results[idx].ndcg_at_k
                )
            per_query_comparisons.append(entry)

        duration = time.perf_counter() - start_time

        return RetrievalComparisonResponse(
            dataset_identifier=dataset_name,
            total_queries=len(active_queries),
            top_k=top_k,
            methods_evaluated=list(reports.keys()),
            method_summaries=method_summaries,
            hybrid_delta_vs_dense=delta_vs_dense,
            hybrid_delta_vs_sparse=delta_vs_sparse,
            reranked_delta_vs_hybrid=delta_reranked,
            per_query_comparisons=per_query_comparisons,
            duration_seconds=round(duration, 4),
        )
