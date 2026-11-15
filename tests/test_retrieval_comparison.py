"""Unit tests for multi-retriever comparative benchmark engine.

Verifies fair comparison across Dense, Sparse, Hybrid, and Reranked Hybrid search.
Zero network access; operates on mock services and synthetic queries.
"""

from unittest.mock import MagicMock

import pytest

from backend.evaluation.retrieval_comparison import RetrievalComparator
from backend.retrieval.retrieval_models import (
    BM25SearchResult,
    EvaluationQuery,
    HybridSearchResponse,
    HybridSearchResult,
    SemanticSearchResult,
)


def _build_test_queries() -> list[EvaluationQuery]:
    return [
        EvaluationQuery(
            query_id="Q1",
            query="Supply chain risks",
            ticker="AAPL",
            relevant_chunk_ids=["chunk_1", "chunk_2"],
            relevance_grades={"chunk_1": 2, "chunk_2": 1},
        ),
        EvaluationQuery(
            query_id="Q2",
            query="Revenue growth drivers",
            ticker="AAPL",
            relevant_chunk_ids=["chunk_3"],
            relevance_grades={"chunk_3": 2},
        ),
    ]


def test_relative_delta_computation() -> None:
    """Test percentage delta computation across positive, zero, and edge cases."""
    # 20% increase
    assert RetrievalComparator._compute_relative_delta(1.2, 1.0) == 20.0
    # 50% decrease
    assert RetrievalComparator._compute_relative_delta(0.5, 1.0) == -50.0
    # Zero baseline with positive test
    assert RetrievalComparator._compute_relative_delta(0.5, 0.0) == 100.0
    # Both zero
    assert RetrievalComparator._compute_relative_delta(0.0, 0.0) == 0.0


def test_retrieval_comparator_fair_benchmark() -> None:
    """Verify that dense, sparse, hybrid, and reranked methods are benchmarked fairly."""
    mock_semantic = MagicMock()
    mock_bm25 = MagicMock()
    mock_hybrid = MagicMock()
    mock_reranker = MagicMock()

    # Dense returns chunk_1 for Q1, chunk_99 for Q2
    mock_semantic.search.side_effect = [
        [
            SemanticSearchResult(
                chunk_id="chunk_1",
                ticker="AAPL",
                company_name="Apple",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_1A",
                section_title="Risk",
                chunk_text="Text",
                similarity_score=0.8,
                source_url="https://www.sec.gov/doc.htm",
            )
        ],
        [
            SemanticSearchResult(
                chunk_id="chunk_99",
                ticker="AAPL",
                company_name="Apple",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_7",
                section_title="MD&A",
                chunk_text="Text",
                similarity_score=0.5,
                source_url="https://www.sec.gov/doc.htm",
            )
        ],
    ]

    # Sparse returns chunk_2 for Q1, chunk_3 for Q2
    mock_bm25.search.side_effect = [
        [
            BM25SearchResult(
                chunk_id="chunk_2",
                ticker="AAPL",
                company_name="Apple",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_1A",
                section_title="Risk",
                chunk_text="Text",
                bm25_score=10.0,
                source_url="https://www.sec.gov/doc.htm",
            )
        ],
        [
            BM25SearchResult(
                chunk_id="chunk_3",
                ticker="AAPL",
                company_name="Apple",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_7",
                section_title="MD&A",
                chunk_text="Text",
                bm25_score=14.0,
                source_url="https://www.sec.gov/doc.htm",
            )
        ],
    ]

    # Hybrid combines chunk_1 and chunk_2 for Q1, and chunk_3 for Q2
    h_cand1 = HybridSearchResult(
        chunk_id="chunk_1",
        ticker="AAPL",
        company_name="Apple",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk",
        chunk_text="Text",
        source_url="https://www.sec.gov/doc.htm",
        rrf_score=0.03,
        retrieval_sources=["dense"],
    )
    h_cand2 = HybridSearchResult(
        chunk_id="chunk_2",
        ticker="AAPL",
        company_name="Apple",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk",
        chunk_text="Text",
        source_url="https://www.sec.gov/doc.htm",
        rrf_score=0.02,
        retrieval_sources=["sparse"],
    )
    h_cand3 = HybridSearchResult(
        chunk_id="chunk_3",
        ticker="AAPL",
        company_name="Apple",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_7",
        section_title="MD&A",
        chunk_text="Text",
        source_url="https://www.sec.gov/doc.htm",
        rrf_score=0.03,
        retrieval_sources=["sparse"],
    )

    mock_hybrid.search.side_effect = [
        HybridSearchResponse(query="Q1", total_results=2, results=[h_cand1, h_cand2]),
        HybridSearchResponse(query="Q2", total_results=1, results=[h_cand3]),
    ]

    mock_reranker.is_available = False

    comparator = RetrievalComparator(
        hybrid_search_service=mock_hybrid,
        semantic_search_service=mock_semantic,
        bm25_search_service=mock_bm25,
        reranker=mock_reranker,
    )

    test_queries = _build_test_queries()
    response = comparator.compare_methods(
        queries=test_queries,
        top_k=2,
        include_reranking=False,
    )

    assert response.total_queries == 2
    assert "dense" in response.method_summaries
    assert "sparse" in response.method_summaries
    assert "hybrid" in response.method_summaries

    assert "precision_delta_pct" in response.hybrid_delta_vs_dense
    assert "recall_delta_pct" in response.hybrid_delta_vs_dense
    assert len(response.per_query_comparisons) == 2


def test_retrieval_comparator_empty_filter() -> None:
    """Verify error raised when ticker filter returns no matching queries."""
    comparator = RetrievalComparator()
    test_queries = _build_test_queries()

    with pytest.raises(ValueError, match="No valid evaluation queries found"):
        comparator.compare_methods(queries=test_queries, ticker_filter="NONEXISTENT")
