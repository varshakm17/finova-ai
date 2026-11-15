"""Unit tests for citation validation, excerpt mapping, and provenance auditing."""

from backend.rag.citation_validator import CitationValidator
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence


def test_extract_citation_ids() -> None:
    validator = CitationValidator()

    # Single citations
    text1 = "Apple reported growth [E1] and strong liquidity [C1]."
    assert validator.extract_citation_ids(text1) == ["E1", "C1"]

    # Multiple citations in single brackets
    text2 = "Risks include international regulation [E1, E2] and currency fluctuations [E3, C2]."
    assert validator.extract_citation_ids(text2) == ["E1", "E2", "E3", "C2"]

    # Deduplication and order preservation
    text3 = (
        "Gross margin was strong [C1]. Also noted in [E1] and confirmed again in [C1]."
    )
    assert validator.extract_citation_ids(text3) == ["C1", "E1"]

    # Empty text
    assert validator.extract_citation_ids("") == []


def test_validate_citations_success() -> None:
    validator = CitationValidator(excerpt_max_chars=100)

    retrieved = [
        RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_001",
            ticker="AAPL",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk Factors",
            chunk_text="Global economic conditions and supply chain dependencies represent principal business risks.",
            source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        )
    ]
    calculations = [
        CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_100",
            metric_name="operating_margin",
            calculated_value=30.13,
            unit="percentage",
            formula="OperatingIncome / TotalRevenue",
            period_end="2023-09-30",
        )
    ]

    answer_text = "Apple faces supply chain vulnerabilities [E1], while sustaining an operating margin of 30.13% [C1]."
    result = validator.validate_citations(answer_text, retrieved, calculations)

    assert result.is_valid is True
    assert result.status == "verified"
    assert len(result.citations) == 2
    assert len(result.unsupported_ids) == 0

    c0 = result.citations[0]
    assert c0.citation_id == "E1"
    assert c0.evidence_type == "filing_passage"
    assert "AAPL 10-K (2023-11-03) ITEM_1A" in c0.source_reference
    assert "https://www.sec.gov" in c0.source_url

    c1 = result.citations[1]
    assert c1.citation_id == "C1"
    assert c1.evidence_type == "calculation_receipt"
    assert "operating_margin" in c1.source_reference
    assert "Formula: OperatingIncome / TotalRevenue" in (c1.excerpt or "")


def test_validate_citations_unsupported_id() -> None:
    validator = CitationValidator()

    retrieved = [
        RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_001",
            ticker="AAPL",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk Factors",
            chunk_text="Global economic risks.",
            source_url="https://www.sec.gov",
        )
    ]

    # Citations contain E1 and hallucinated E99
    answer_text = "Reported risks [E1] and unspecified foreign litigation [E99]."
    result = validator.validate_citations(answer_text, retrieved, [])

    assert result.is_valid is False
    assert result.status == "partially_supported"
    assert "E99" in result.unsupported_ids
    assert len(result.warnings) > 0
    assert "unsupported citation identifier(s): E99" in result.warnings[0]


def test_validate_citations_all_unsupported() -> None:
    validator = CitationValidator()
    answer_text = "Completely hallucinated citation claims [E88]."
    result = validator.validate_citations(answer_text, [], [])

    assert result.is_valid is False
    assert result.status == "citation_validation_failed"
    assert result.unsupported_ids == ["E88"]


def test_validate_citations_missing_citations() -> None:
    validator = CitationValidator()

    retrieved = [
        RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_001",
            ticker="AAPL",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk Factors",
            chunk_text="Risk factor details.",
            source_url="https://www.sec.gov",
        )
    ]

    # Factual answer without any [E1] or [C1] citations
    answer_text = "Apple operates primarily in consumer electronics and software services with international distributors."
    result = validator.validate_citations(answer_text, retrieved, [])

    assert result.status == "partially_supported"
    assert any("zero verified evidence citations" in w for w in result.warnings)


def test_validate_citations_insufficient_evidence_response() -> None:
    validator = CitationValidator()

    retrieved = [
        RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_001",
            ticker="AAPL",
            company_name="Apple Inc.",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk Factors",
            chunk_text="Risk factor details.",
            source_url="https://www.sec.gov",
        )
    ]

    # Model reports insufficient evidence - absence of citations is expected and valid
    answer_text = "The available SEC filing disclosures do not provide sufficient evidence to answer this question."
    result = validator.validate_citations(answer_text, retrieved, [])

    assert result.is_valid is True
    assert result.status == "verified"
    assert len(result.warnings) == 0
