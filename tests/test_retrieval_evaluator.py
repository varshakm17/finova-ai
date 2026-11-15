"""Unit tests for deterministic information retrieval evaluation metrics.

Tests Precision@K, Recall@K, MRR, MAP, NDCG@K, Coverage, and macro/micro aggregation.
Zero network access; pure deterministic mathematics.
"""

import json
from pathlib import Path

import pytest

from backend.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
    calculate_average_precision,
    calculate_ndcg_at_k,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
)
from backend.retrieval.retrieval_models import EvaluationQuery


def test_precision_at_k_deterministic() -> None:
    """Test Precision@K across perfect, partial, and zero hit cases."""
    relevant = {"doc_1", "doc_2"}

    # Perfect top-2
    assert calculate_precision_at_k(["doc_1", "doc_2", "doc_3"], relevant, k=2) == 1.0

    # Partial top-2 (1 out of 2)
    assert calculate_precision_at_k(["doc_1", "doc_3"], relevant, k=2) == 0.5

    # Zero hits in top-2
    assert calculate_precision_at_k(["doc_3", "doc_4"], relevant, k=2) == 0.0

    # Empty retrieved
    assert calculate_precision_at_k([], relevant, k=5) == 0.0

    # Invalid k
    with pytest.raises(ValueError, match="Cutoff k must be positive"):
        calculate_precision_at_k(["doc_1"], relevant, k=0)


def test_precision_at_k_deduplication() -> None:
    """Test that duplicate retrieved IDs do not artificially inflate Precision@K."""
    relevant = {"doc_1"}
    # doc_1 appears twice; should only count as 1 hit out of k=2
    retrieved = ["doc_1", "doc_1", "doc_2"]
    assert calculate_precision_at_k(retrieved, relevant, k=2) == 0.5


def test_recall_at_k_deterministic() -> None:
    """Test Recall@K under different cutoff and ground truth sizes."""
    relevant = {"doc_1", "doc_2", "doc_3", "doc_4"}

    # 2 out of 4 found in top-3
    retrieved = ["doc_1", "doc_99", "doc_2"]
    assert calculate_recall_at_k(retrieved, relevant, k=3) == 0.5

    # All found in top-4
    retrieved_all = ["doc_1", "doc_2", "doc_3", "doc_4"]
    assert calculate_recall_at_k(retrieved_all, relevant, k=4) == 1.0

    # No relevant items exist in ground truth
    assert calculate_recall_at_k(retrieved, set(), k=3) == 0.0

    # Empty retrieved
    assert calculate_recall_at_k([], relevant, k=5) == 0.0

    with pytest.raises(ValueError, match="Cutoff k must be positive"):
        calculate_recall_at_k(["doc_1"], relevant, k=-1)


def test_reciprocal_rank_deterministic() -> None:
    """Test Reciprocal Rank for rank 1, rank 2, rank 3, and not found."""
    relevant = {"doc_target"}

    # First position
    assert calculate_reciprocal_rank(["doc_target", "doc_other"], relevant) == 1.0

    # Second position
    assert calculate_reciprocal_rank(["doc_other", "doc_target"], relevant) == 0.5

    # Third position
    assert calculate_reciprocal_rank(
        ["doc_1", "doc_2", "doc_target"], relevant
    ) == pytest.approx(1.0 / 3.0)

    # Not found
    assert calculate_reciprocal_rank(["doc_1", "doc_2"], relevant) == 0.0

    # Empty
    assert calculate_reciprocal_rank([], relevant) == 0.0
    assert calculate_reciprocal_rank(["doc_1"], set()) == 0.0


def test_average_precision_deterministic() -> None:
    """Test Average Precision with step-by-step verification."""
    relevant = {"doc_1", "doc_2"}

    # Rank 1: doc_1 (rel, P@1 = 1/1 = 1.0)
    # Rank 2: doc_3 (not rel)
    # Rank 3: doc_2 (rel, P@3 = 2/3 = 0.6667)
    # AP = (1.0 + 2/3) / 2 = 1.6667 / 2 = 0.8333333333333333
    retrieved = ["doc_1", "doc_3", "doc_2"]
    ap = calculate_average_precision(retrieved, relevant)
    assert ap == pytest.approx((1.0 + (2.0 / 3.0)) / 2.0)

    # No relevant items in ground truth
    assert calculate_average_precision(retrieved, set()) == 0.0
    # Empty retrieved
    assert calculate_average_precision([], relevant) == 0.0


def test_ndcg_at_k_binary_and_graded() -> None:
    """Test NDCG@K under binary relevance and graded relevance."""
    relevant = {"doc_1", "doc_2"}
    grades = {"doc_1": 2, "doc_2": 1}

    # Ideal ranking: doc_1 then doc_2
    ideal_retrieved = ["doc_1", "doc_2", "doc_3"]
    assert (
        calculate_ndcg_at_k(ideal_retrieved, relevant, k=3, relevance_grades=grades)
        == 1.0
    )

    # Sub-optimal ranking: doc_2 then doc_1
    suboptimal = ["doc_2", "doc_1", "doc_3"]
    ndcg_sub = calculate_ndcg_at_k(suboptimal, relevant, k=3, relevance_grades=grades)
    assert 0.0 < ndcg_sub < 1.0

    # Non-relevant first: doc_3 then doc_1 then doc_2
    worst = ["doc_3", "doc_1", "doc_2"]
    ndcg_worst = calculate_ndcg_at_k(worst, relevant, k=3, relevance_grades=grades)
    assert ndcg_worst < ndcg_sub

    # Binary relevance fallback (no grades provided)
    ndcg_binary = calculate_ndcg_at_k(["doc_1", "doc_2"], relevant, k=2)
    assert ndcg_binary == 1.0

    # Empty sets
    assert calculate_ndcg_at_k([], relevant, k=5) == 0.0
    assert calculate_ndcg_at_k(["doc_1"], set(), k=5) == 0.0

    with pytest.raises(ValueError, match="Cutoff k must be positive"):
        calculate_ndcg_at_k(["doc_1"], relevant, k=0)


def test_dataset_loader_and_evaluation(tmp_path: Path) -> None:
    """Test loading JSON dataset and running multi-query evaluation."""
    queries_data = [
        {
            "query_id": "Q1",
            "query": "Risk factors query",
            "ticker": "AAPL",
            "relevant_chunk_ids": ["c1", "c2"],
            "relevance_grades": {"c1": 2, "c2": 1},
            "dataset_type": "synthetic",
        },
        {
            "query_id": "Q2",
            "query": "Revenue discussion query",
            "ticker": "AAPL",
            "relevant_chunk_ids": ["c3"],
            "dataset_type": "synthetic",
        },
    ]

    dataset_file = tmp_path / "test_queries.json"
    dataset_file.write_text(json.dumps(queries_data), encoding="utf-8")

    evaluator = RetrievalEvaluator()
    loaded_queries = evaluator.load_dataset(dataset_file)
    assert len(loaded_queries) == 2
    assert loaded_queries[0].query_id == "Q1"

    # Mock retriever: Q1 gets c1, c9, c2; Q2 gets c3, c8
    def mock_retriever(q: EvaluationQuery, top_k: int) -> tuple[list[str], float]:
        if q.query_id == "Q1":
            return ["c1", "c9", "c2"][:top_k], 12.5
        return ["c3", "c8"][:top_k], 8.0

    report = evaluator.evaluate_retriever(
        retriever_fn=mock_retriever,
        queries=loaded_queries,
        k=2,
        dataset_identifier="test_queries.json",
        method_name="mock_hybrid",
    )

    assert report.evaluation_method == "mock_hybrid"
    assert report.metrics.evaluated_queries_count == 2
    assert report.metrics.coverage == 1.0
    assert len(report.per_query_results) == 2

    # Q1: retrieved top-2 = ['c1', 'c9']. Hits in rel {'c1', 'c2'}: 'c1' (1 hit). P@2 = 0.5, R@2 = 0.5
    # Q2: retrieved top-2 = ['c3', 'c8']. Hits in rel {'c3'}: 'c3' (1 hit). P@2 = 0.5, R@2 = 1.0
    # Macro P@2 = (0.5 + 0.5) / 2 = 0.5
    assert report.metrics.precision_at_k == 0.5
    # Macro R@2 = (0.5 + 1.0) / 2 = 0.75
    assert report.metrics.recall_at_k == 0.75
    assert report.metrics.mrr == 1.0


def test_dataset_loader_invalid_file(tmp_path: Path) -> None:
    """Test error handling when dataset file is missing or invalid."""
    evaluator = RetrievalEvaluator()

    with pytest.raises(FileNotFoundError):
        evaluator.load_dataset(tmp_path / "non_existent.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("invalid json content", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse evaluation dataset"):
        evaluator.load_dataset(bad_json)


def test_evaluation_with_empty_ground_truth() -> None:
    """Test that queries with empty relevant IDs are skipped and reported."""
    evaluator = RetrievalEvaluator()
    queries = [
        EvaluationQuery(
            query_id="EMPTY",
            query="Empty query",
            relevant_chunk_ids=[],
        )
    ]

    def mock_retriever(q: EvaluationQuery, top_k: int) -> tuple[list[str], float]:
        return ["c1", "c2"], 5.0

    report = evaluator.evaluate_retriever(
        retriever_fn=mock_retriever,
        queries=queries,
        k=5,
    )
    assert report.metrics.evaluated_queries_count == 0
    assert report.metrics.skipped_queries_count == 1
    assert len(report.warnings) > 0
