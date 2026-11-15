"""Unit tests for Query-Level Evidence Report Generator.

Verifies complete LLM-independent report assembly, statutory provenance preservation,
reranking metadata, validation auditing, and SEC source link extraction.
Zero network access; pure deterministic orchestration.
"""

from unittest.mock import MagicMock

from backend.evaluation.evidence_report import EvidenceReportGenerator
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.retrieval.retrieval_models import (
    HybridSearchResponse,
    HybridSearchResult,
    RerankedSearchResult,
)


def _create_mock_candidate(chunk_id: str, text: str) -> HybridSearchResult:
    return HybridSearchResult(
        chunk_id=chunk_id,
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text=text,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/doc.htm",
        dense_rank=1,
        dense_score=0.82,
        sparse_rank=1,
        bm25_score=14.5,
        rrf_score=0.032,
        retrieval_sources=["dense", "sparse"],
    )


def test_evidence_report_generator_without_reranking() -> None:
    """Verify evidence report generation without reranking stage."""
    mock_hybrid = MagicMock()
    c1 = _create_mock_candidate(
        "c1",
        "Risk disclosure regarding overseas suppliers and single source manufacturing.",
    )
    c2 = _create_mock_candidate(
        "c2",
        "Operating expense discussion regarding R&D outlays and engineering headcount.",
    )
    mock_hybrid.search.return_value = HybridSearchResponse(
        query="What are the risks?",
        total_results=2,
        results=[c1, c2],
    )

    validator = EvidenceQualityValidator()
    report_gen = EvidenceReportGenerator(
        hybrid_search_service=mock_hybrid,
        validator=validator,
    )

    report = report_gen.generate_report(
        query="What are the risks?",
        top_k=2,
        apply_reranking=False,
    )

    assert report.query == "What are the risks?"
    assert report.retrieval_method == "hybrid"
    assert report.reranker_applied is False
    assert len(report.ranked_candidates) == 2
    assert report.ranked_candidates[0]["chunk_id"] == "c1"
    assert len(report.sec_source_links) == 1
    assert report.validation_summary.overall_status == "valid"


def test_evidence_report_generator_with_reranking() -> None:
    """Verify evidence report generation incorporating cross-encoder reranking metadata."""
    mock_hybrid = MagicMock()
    c1 = _create_mock_candidate("c1", "Risk disclosure 1")
    c2 = _create_mock_candidate("c2", "Risk disclosure 2")
    mock_hybrid.search.return_value = HybridSearchResponse(
        query="Component shortages",
        total_results=2,
        results=[c1, c2],
    )

    mock_reranker = MagicMock()
    mock_reranker.is_available = True
    reranked_cand1 = RerankedSearchResult(
        chunk_id="c2",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Risk Factors",
        chunk_text="Risk disclosure 2",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/doc.htm",
        original_rank=2,
        rerank_rank=1,
        rerank_score=3.8,
        retrieval_sources=["dense", "sparse"],
    )
    mock_reranker.rerank.return_value = (
        [reranked_cand1],
        {"reranker_applied": True, "model_name": "mock-cross-encoder"},
    )

    validator = EvidenceQualityValidator()
    report_gen = EvidenceReportGenerator(
        hybrid_search_service=mock_hybrid,
        reranker=mock_reranker,
        validator=validator,
    )

    report = report_gen.generate_report(
        query="Component shortages",
        top_k=1,
        apply_reranking=True,
    )

    assert report.retrieval_method == "hybrid_reranked"
    assert report.reranker_applied is True
    assert report.reranker_model == "mock-cross-encoder"
    assert len(report.ranked_candidates) == 1
    assert report.ranked_candidates[0]["chunk_id"] == "c2"
    assert report.ranked_candidates[0]["rerank_score"] == 3.8
    assert report.ranked_candidates[0]["original_rank"] == 2
