"""Unit tests for Evidence Quality Validator.

Verifies deterministic provenance completeness, SEC domain validation,
stored document consistency, exact and near-duplicate detection, and temporal divergence.
Zero network access; pure deterministic auditing.
"""

from unittest.mock import MagicMock

from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.retrieval.retrieval_models import HybridSearchResult


def _create_candidate(
    chunk_id: str,
    ticker: str = "AAPL",
    cik: str = "0000320193",
    filing_type: str = "10-K",
    filing_date: str = "2023-11-03",
    report_date: str = "2023-09-30",
    accession: str = "0000320193-23-000106",
    section: str = "ITEM_1A",
    source_url: str = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
    text: str = "Supply chain and single source manufacturing risks.",
) -> HybridSearchResult:
    return HybridSearchResult(
        chunk_id=chunk_id,
        ticker=ticker,
        company_name="Apple Inc.",
        cik=cik,
        filing_type=filing_type,
        filing_date=filing_date,
        report_date=report_date,
        accession_number=accession,
        section_identifier=section,
        section_title="Risk Factors",
        chunk_text=text,
        source_url=source_url,
        dense_rank=1,
        dense_score=0.8,
        sparse_rank=1,
        bm25_score=12.0,
        rrf_score=0.03,
        retrieval_sources=["dense", "sparse"],
    )


def test_provenance_completeness_valid() -> None:
    """Verify that a candidate with all required statutory fields passes as valid."""
    validator = EvidenceQualityValidator()
    cand = _create_candidate("c1")

    res = validator.validate_chunks([cand])
    assert res.total_chunks_inspected == 1
    assert res.valid_count == 1
    assert res.overall_status == "valid"
    assert res.chunk_validations[0].status == "valid"
    assert res.chunk_validations[0].provenance_complete is True


def test_provenance_incomplete_missing_fields() -> None:
    """Verify missing accession number or ticker flags incomplete provenance."""
    validator = EvidenceQualityValidator()
    # Missing accession and ticker
    cand = _create_candidate("c_bad", ticker="", accession="")

    res = validator.validate_chunks([cand])
    assert res.valid_count == 0
    assert res.warning_count == 1
    assert res.chunk_validations[0].status == "incomplete_provenance"
    assert res.chunk_validations[0].provenance_complete is False


def test_sec_url_whitelist_validation() -> None:
    """Verify valid SEC EDGAR URLs pass and unapproved domains raise warnings."""
    validator = EvidenceQualityValidator()

    # Valid official SEC URLs
    assert validator.is_approved_sec_url(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/doc.htm"
    )
    assert validator.is_approved_sec_url(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )

    # Invalid / unauthorized domain
    assert not validator.is_approved_sec_url(
        "https://malicious-site.com/edgar/fake.htm"
    )
    assert not validator.is_approved_sec_url("")
    assert not validator.is_approved_sec_url(None)

    cand_bad_url = _create_candidate(
        "c_bad_url", source_url="https://external-blog.com/financials.htm"
    )
    res = validator.validate_chunks([cand_bad_url])
    assert res.chunk_validations[0].source_domain_valid is False
    assert any(
        "does not match an approved SEC EDGAR domain" in w
        for w in res.chunk_validations[0].warnings
    )


def test_duplicate_chunk_detection() -> None:
    """Verify exact duplicate chunk ID and high text overlap are flagged."""
    validator = EvidenceQualityValidator()

    # Duplicate chunk ID
    c1 = _create_candidate("duplicate_id", text="Unique risk text 1.")
    c2 = _create_candidate("duplicate_id", text="Unique risk text 2.")

    res = validator.validate_chunks([c1, c2])
    assert res.chunk_validations[1].is_duplicate is True
    assert res.chunk_validations[1].status == "possible_duplicate"
    assert len(res.duplicate_clusters) == 1

    # Overlapping text similarity (Jaccard > 0.85)
    c3 = _create_candidate(
        "c3",
        text="The company relies heavily on single source suppliers for critical components.",
    )
    c4 = _create_candidate(
        "c4",
        text="The company relies heavily on single source suppliers for critical component parts.",
    )
    res_overlap = validator.validate_chunks([c3, c4])
    assert res_overlap.chunk_validations[1].is_duplicate is True
    assert res_overlap.chunk_validations[1].status == "possible_duplicate"


def test_temporal_divergence_detection() -> None:
    """Verify multi-period evidence raises temporal warnings so LLMs do not conflate periods."""
    validator = EvidenceQualityValidator()

    # Chunk 1 refers to FY2022, Chunk 2 refers to FY2023
    c1 = _create_candidate(
        "c1",
        accession="0000320193-22-000108",
        report_date="2022-09-30",
        filing_date="2022-10-28",
        text="Supply chain disruptions in fiscal 2022.",
    )
    c2 = _create_candidate(
        "c2",
        accession="0000320193-23-000106",
        report_date="2023-09-30",
        filing_date="2023-11-03",
        text="Component cost inflation and logistics challenges in fiscal 2023.",
    )

    res = validator.validate_chunks([c1, c2])
    assert len(res.distinct_reporting_periods) == 2
    assert res.chunk_validations[0].status == "temporal_mismatch"
    assert res.chunk_validations[1].status == "temporal_mismatch"
    assert any("Multi-period evidence detected" in note for note in res.summary_notes)


def test_document_storage_consistency_check() -> None:
    """Verify metadata consistency against DocumentStorage records."""
    mock_storage = MagicMock()
    # Mock document has ticker 'MSFT' while chunk claims 'AAPL'
    mock_doc = MagicMock()
    mock_doc.ticker = "MSFT"
    mock_doc.filing_type = "10-K"
    mock_storage.get_document_by_accession.return_value = mock_doc

    validator = EvidenceQualityValidator(document_storage=mock_storage)
    cand = _create_candidate(
        "c_mismatch", ticker="AAPL", accession="0000789019-23-000010"
    )

    res = validator.validate_chunks([cand])
    assert res.chunk_validations[0].status == "source_mismatch"
    assert res.chunk_validations[0].document_matched is False
    assert any("Metadata mismatch" in w for w in res.chunk_validations[0].warnings)


def test_empty_candidates_evidence_validation() -> None:
    """Verify empty candidates input produces clean valid response."""
    validator = EvidenceQualityValidator()
    res = validator.validate_chunks([])
    assert res.total_chunks_inspected == 0
    assert res.valid_count == 0
    assert res.overall_status == "valid"
