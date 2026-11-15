"""Deterministic Information Retrieval Evaluation Engine for Finova AI.

Calculates standard information retrieval metrics:
- Precision@K
- Recall@K, Recall@5, Recall@10, Recall@20
- Mean Reciprocal Rank (MRR)
- Mean Average Precision (MAP)
- Normalized Discounted Cumulative Gain (NDCG@K)
- Query Coverage
- Macro and Micro aggregations

Supports both binary ground truth and graded relevance judgments.
Includes offline synthetic query benchmark suites and robust JSON dataset loading.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.retrieval.retrieval_models import (
    EvaluationQuery,
    PerQueryMetric,
    RetrievalEvaluationReport,
    RetrievalMetricResult,
)
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("retrieval_evaluator")


def calculate_precision_at_k(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """Calculate Precision@K: (Relevant retrieved in top K) / K.

    Deduplicates retrieved IDs preserving first occurrence rank.

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of known relevant document/chunk IDs.
        k: Rank cutoff (must be >= 1).

    Returns:
        float: Precision at cutoff k in range [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError(f"Cutoff k must be positive, got {k}")
    if not retrieved_ids:
        return 0.0

    # Deduplicate preserving first appearance order
    seen: set[str] = set()
    deduped: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(doc_id)

    top_k_docs = deduped[:k]
    rel_count = sum(1 for doc_id in top_k_docs if doc_id in relevant_ids)
    return rel_count / float(k)


def calculate_recall_at_k(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """Calculate Recall@K: (Relevant retrieved in top K) / (Total known relevant).

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of known relevant document/chunk IDs.
        k: Rank cutoff (must be >= 1).

    Returns:
        float: Recall at cutoff k in range [0.0, 1.0]. Returns 0.0 if no relevant items exist.
    """
    if k <= 0:
        raise ValueError(f"Cutoff k must be positive, got {k}")
    if not relevant_ids or not retrieved_ids:
        return 0.0

    seen: set[str] = set()
    deduped: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(doc_id)

    top_k_docs = deduped[:k]
    rel_count = sum(1 for doc_id in top_k_docs if doc_id in relevant_ids)
    return rel_count / float(len(relevant_ids))


def calculate_reciprocal_rank(
    retrieved_ids: list[str],
    relevant_ids: set[str],
) -> float:
    """Calculate Reciprocal Rank (1 / rank) for the first relevant retrieved document.

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of known relevant document/chunk IDs.

    Returns:
        float: Reciprocal rank (1.0 for rank 1, 0.5 for rank 2, etc.), or 0.0 if none found.
    """
    if not relevant_ids or not retrieved_ids:
        return 0.0

    seen: set[str] = set()
    deduped: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(doc_id)

    for rank_idx, doc_id in enumerate(deduped, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank_idx
    return 0.0


def calculate_average_precision(
    retrieved_ids: list[str],
    relevant_ids: set[str],
) -> float:
    """Calculate Average Precision (AP) for a single query.

    AP = (1 / |Relevant|) * sum_{i=1}^N (Precision@i * rel(i))

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of known relevant document/chunk IDs.

    Returns:
        float: Average Precision in range [0.0, 1.0]. Returns 0.0 if no relevant items exist.
    """
    if not relevant_ids or not retrieved_ids:
        return 0.0

    seen: set[str] = set()
    deduped: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(doc_id)

    cumulative_hits = 0
    running_precision_sum = 0.0

    for i, doc_id in enumerate(deduped, start=1):
        if doc_id in relevant_ids:
            cumulative_hits += 1
            precision_at_i = cumulative_hits / float(i)
            running_precision_sum += precision_at_i

    return running_precision_sum / float(len(relevant_ids))


def calculate_ndcg_at_k(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    k: int,
    relevance_grades: dict[str, int] | None = None,
) -> float:
    """Calculate Normalized Discounted Cumulative Gain (NDCG@K).

    Uses the standard exponential gain formulation:
        DCG@K = sum_{i=1}^{min(K, |retrieved|)} (2^{rel_i} - 1) / log2(i + 1)
        IDCG@K = sum_{i=1}^{min(K, |relevant|)} (2^{ideal_rel_i} - 1) / log2(i + 1)
        NDCG@K = DCG@K / IDCG@K

    Args:
        retrieved_ids: Ordered list of retrieved document/chunk IDs.
        relevant_ids: Set of known relevant document IDs.
        k: Rank cutoff (must be >= 1).
        relevance_grades: Optional mapping from chunk_id to integer grade (>= 0).
            If omitted or missing, relevant IDs receive grade 1, others 0.

    Returns:
        float: NDCG@K in range [0.0, 1.0]. Returns 0.0 if IDCG@K is 0.
    """
    if k <= 0:
        raise ValueError(f"Cutoff k must be positive, got {k}")
    if not relevant_ids or not retrieved_ids:
        return 0.0

    grades = relevance_grades or {}

    def get_grade(doc_id: str) -> int:
        if doc_id in grades:
            return max(0, grades[doc_id])
        return 1 if doc_id in relevant_ids else 0

    seen: set[str] = set()
    deduped: list[str] = []
    for doc_id in retrieved_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            deduped.append(doc_id)

    top_k_docs = deduped[:k]

    # Calculate DCG@K
    dcg = 0.0
    for i, doc_id in enumerate(top_k_docs, start=1):
        rel = get_grade(doc_id)
        if rel > 0:
            gain = (2.0**rel) - 1.0
            discount = math.log2(i + 1.0)
            dcg += gain / discount

    # Calculate Ideal DCG@K (IDCG)
    all_relevant_grades = [get_grade(doc_id) for doc_id in relevant_ids]
    all_relevant_grades.sort(reverse=True)
    top_ideal = all_relevant_grades[:k]

    idcg = 0.0
    for i, ideal_rel in enumerate(top_ideal, start=1):
        if ideal_rel > 0:
            gain = (2.0**ideal_rel) - 1.0
            discount = math.log2(i + 1.0)
            idcg += gain / discount

    if idcg <= 0.0:
        return 0.0

    return min(1.0, dcg / idcg)


class RetrievalEvaluator:
    """Evaluates search systems deterministically against benchmark datasets."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def load_dataset(dataset_path: str | Path) -> list[EvaluationQuery]:
        """Load and validate an evaluation dataset from JSON file.

        Supports both a root JSON array of query objects and a dict with a 'queries' key.
        """
        path = Path(dataset_path)
        if not path.is_file():
            raise FileNotFoundError(f"Evaluation dataset file not found at: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise ValueError(f"Failed to parse evaluation dataset JSON: {exc}") from exc

        query_list: list[dict[str, Any]]
        if isinstance(data, list):
            query_list = data
        elif (
            isinstance(data, dict)
            and "queries" in data
            and isinstance(data["queries"], list)
        ):
            query_list = data["queries"]
        else:
            raise ValueError(
                "Evaluation dataset must be a JSON array or contain a 'queries' list."
            )

        evaluation_queries: list[EvaluationQuery] = []
        for idx, item in enumerate(query_list):
            try:
                eq = EvaluationQuery(**item)
                evaluation_queries.append(eq)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid evaluation query at index %d: %s", idx, exc
                )

        return evaluation_queries

    def evaluate_query(
        self,
        query: EvaluationQuery,
        retrieved_ids: list[str],
        k: int = 5,
        latency_ms: float = 0.0,
    ) -> PerQueryMetric:
        """Compute all IR metrics for a single query."""
        relevant_set = set(query.relevant_chunk_ids)

        p_at_k = calculate_precision_at_k(retrieved_ids, relevant_set, k)
        r_at_k = calculate_recall_at_k(retrieved_ids, relevant_set, k)
        rr = calculate_reciprocal_rank(retrieved_ids, relevant_set)
        ap = calculate_average_precision(retrieved_ids, relevant_set)
        ndcg = calculate_ndcg_at_k(
            retrieved_ids, relevant_set, k, query.relevance_grades
        )

        # Count relevant items in top-k
        seen: set[str] = set()
        deduped: list[str] = []
        for d in retrieved_ids:
            if d not in seen:
                seen.add(d)
                deduped.append(d)
        top_k_deduped = deduped[:k]
        rel_in_top_k = sum(1 for d in top_k_deduped if d in relevant_set)

        return PerQueryMetric(
            query_id=query.query_id,
            query=query.query,
            expected_relevant_count=len(relevant_set),
            retrieved_count=len(retrieved_ids),
            relevant_retrieved_count=rel_in_top_k,
            precision_at_k=round(p_at_k, 4),
            recall_at_k=round(r_at_k, 4),
            reciprocal_rank=round(rr, 4),
            average_precision=round(ap, 4),
            ndcg_at_k=round(ndcg, 4),
            retrieved_chunk_ids=retrieved_ids[:k],
            latency_ms=round(latency_ms, 2),
        )

    def evaluate_retriever(
        self,
        retriever_fn: Callable[[EvaluationQuery, int], tuple[list[str], float]],
        queries: list[EvaluationQuery],
        k: int = 5,
        dataset_identifier: str = "retrieval_queries.json",
        method_name: str = "retriever",
        dataset_type: str = "synthetic",
    ) -> RetrievalEvaluationReport:
        """Run full offline evaluation over a list of queries.

        Args:
            retriever_fn: Callable taking (query_obj, top_k) and returning (retrieved_chunk_ids, latency_ms).
            queries: List of EvaluationQuery instances.
            k: Primary rank cutoff for Precision@K, Recall@K, NDCG@K.
            dataset_identifier: Name/path of dataset.
            method_name: Name of retrieval modality (e.g. 'dense', 'bm25', 'hybrid', 'hybrid_reranked').
            dataset_type: 'synthetic' or 'curated'.

        Returns:
            RetrievalEvaluationReport containing aggregated and per-query metrics.
        """
        start_time = time.perf_counter()
        per_query_results: list[PerQueryMetric] = []
        warnings: list[str] = []

        # Tracking for Recall@5, 10, 20
        r5_scores: list[float] = []
        r10_scores: list[float] = []
        r20_scores: list[float] = []

        total_relevant_sum = 0
        total_retrieved_sum = 0
        total_hits_at_k_sum = 0
        queries_with_results = 0
        skipped_queries = 0

        for q in queries:
            rel_set = set(q.relevant_chunk_ids)
            if not rel_set:
                skipped_queries += 1
                warnings.append(
                    f"Query '{q.query_id}' skipped: no ground-truth relevant IDs."
                )
                continue

            # Over-fetch up to max(20, k) to allow computing Recall@5, 10, 20
            fetch_k = max(20, k)
            try:
                retrieved_ids, lat_ms = retriever_fn(q, fetch_k)
            except Exception as exc:
                logger.error("Error retrieving for query %s: %s", q.query_id, exc)
                retrieved_ids, lat_ms = [], 0.0
                warnings.append(f"Retriever raised exception for '{q.query_id}': {exc}")

            if retrieved_ids:
                queries_with_results += 1

            # Primary per-query metrics at k
            qm = self.evaluate_query(q, retrieved_ids, k=k, latency_ms=lat_ms)
            per_query_results.append(qm)

            # Additional recall cutoffs
            r5_scores.append(calculate_recall_at_k(retrieved_ids, rel_set, 5))
            r10_scores.append(calculate_recall_at_k(retrieved_ids, rel_set, 10))
            r20_scores.append(calculate_recall_at_k(retrieved_ids, rel_set, 20))

            # Micro sums
            total_relevant_sum += len(rel_set)
            total_retrieved_sum += min(k, len(retrieved_ids))
            total_hits_at_k_sum += qm.relevant_retrieved_count

        evaluated_count = len(per_query_results)
        if evaluated_count == 0:
            total_duration = time.perf_counter() - start_time
            empty_metrics = RetrievalMetricResult(
                precision_at_k=0.0,
                recall_at_k=0.0,
                recall_at_5=0.0,
                recall_at_10=0.0,
                recall_at_20=0.0,
                mrr=0.0,
                map_score=0.0,
                ndcg_at_k=0.0,
                coverage=0.0,
                k=k,
                evaluated_queries_count=0,
                skipped_queries_count=skipped_queries,
                macro_precision=0.0,
                micro_precision=0.0,
                macro_recall=0.0,
                micro_recall=0.0,
            )
            return RetrievalEvaluationReport(
                report_id=f"rep_{uuid.uuid4().hex[:12]}",
                evaluation_method=method_name,
                dataset_identifier=dataset_identifier,
                dataset_type=dataset_type,
                metrics=empty_metrics,
                per_query_results=[],
                execution_time_seconds=round(total_duration, 4),
                warnings=warnings or ["No valid queries were evaluated."],
            )

        # Macro averages
        macro_p = sum(r.precision_at_k for r in per_query_results) / evaluated_count
        macro_r = sum(r.recall_at_k for r in per_query_results) / evaluated_count
        macro_r5 = sum(r5_scores) / evaluated_count
        macro_r10 = sum(r10_scores) / evaluated_count
        macro_r20 = sum(r20_scores) / evaluated_count
        mrr = sum(r.reciprocal_rank for r in per_query_results) / evaluated_count
        map_score = (
            sum(r.average_precision for r in per_query_results) / evaluated_count
        )
        macro_ndcg = sum(r.ndcg_at_k for r in per_query_results) / evaluated_count
        coverage = queries_with_results / float(len(queries))

        # Micro averages
        micro_p = (
            (total_hits_at_k_sum / float(evaluated_count * k))
            if (evaluated_count * k) > 0
            else 0.0
        )
        micro_r = (
            (total_hits_at_k_sum / float(total_relevant_sum))
            if total_relevant_sum > 0
            else 0.0
        )

        total_duration = time.perf_counter() - start_time

        aggregated_metrics = RetrievalMetricResult(
            precision_at_k=round(macro_p, 4),
            recall_at_k=round(macro_r, 4),
            recall_at_5=round(macro_r5, 4),
            recall_at_10=round(macro_r10, 4),
            recall_at_20=round(macro_r20, 4),
            mrr=round(mrr, 4),
            map_score=round(map_score, 4),
            ndcg_at_k=round(macro_ndcg, 4),
            coverage=round(coverage, 4),
            k=k,
            evaluated_queries_count=evaluated_count,
            skipped_queries_count=skipped_queries,
            macro_precision=round(macro_p, 4),
            micro_precision=round(micro_p, 4),
            macro_recall=round(macro_r, 4),
            micro_recall=round(micro_r, 4),
        )

        return RetrievalEvaluationReport(
            report_id=f"rep_{uuid.uuid4().hex[:12]}",
            evaluation_method=method_name,
            dataset_identifier=dataset_identifier,
            dataset_type=dataset_type,
            metrics=aggregated_metrics,
            per_query_results=per_query_results,
            execution_time_seconds=round(total_duration, 4),
            warnings=warnings,
        )
