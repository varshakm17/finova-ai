"""Tests for Session 18.1 Verification Audit and Remediation.

Covers regression verification for:
1. FinancialExtractor multi-tag candidate iteration across XBRL taxonomy shifts (NVDA case).
2. ClaimExtractor table row filtering and word-boundary truncation (TSLA/NVDA table cases).
3. ClaimExtractor placeholder and italicized notice exclusion.
4. NumericVerifier presentation rounding tolerance (e.g., 0.22% vs 0.2229%).
5. ResearchCoordinator section identifier normalization (underscores and hyphens in ITEM_1A, ITEM_7, ITEM_1).
6. ResearchCoordinator strict chunk provenance (rejection of untraceable/synthetic IDs).
7. ReportAgent takeaway evidence citation grounding in Section 7.
"""

from backend.agents.report_agent import ReportAgent
from backend.agents.research_coordinator import ResearchCoordinator
from backend.data.financial_extractor import FinancialExtractor
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.numeric_verifier import NumericVerifier


def test_financial_extractor_multi_tag_fallback():
    """Verify FinancialExtractor extracts facts across multiple tags without early break."""
    extractor = FinancialExtractor()
    mock_facts = {
        "cik": 1045810,
        "entityName": "NVIDIA CORP",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2022, "fp": "FY", "val": 26914000000, "end": "2022-01-30"}
                        ]
                    }
                },
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2023, "fp": "FY", "val": 26974000000, "end": "2023-01-29"},
                            {"form": "10-K", "fy": 2024, "fp": "FY", "val": 60922000000, "end": "2024-01-28"}
                        ]
                    }
                }
            }
        }
    }
    obs = extractor.extract_company_facts(mock_facts, "NVDA")
    revenue_obs = [o for o in obs if o.metric_name.lower() == "revenue"]
    assert len(revenue_obs) == 3
    years = {o.fiscal_year for o in revenue_obs}
    assert years == {2022, 2023, 2024}


def test_claim_extractor_table_row_and_tabular_filtering():
    """Verify that table rows and tabular fragments are excluded from claim extraction."""
    extractor = ClaimExtractor()
    text = (
        "- Business Operations [E1]: Microsoft Corporation develops software and cloud services [E1].\n"
        "- Management Discussion [E10]: | 51 | % Total automotive revenues | 82,419 | 71,462 | 47,232 | 10,957 | 15 | %\n"
        "- Management Discussion [E11]: In FY2023, automotive segment deliveries increased substantially [E11].\n"
        "| Col1 | Col2 | Col3 |\n"
        "| --- | --- | --- |\n"
        "| 100 | 200 | 300 |\n"
    )
    result = extractor.extract_claims(text)
    claims = [c.claim_text for c in result.claims]

    assert any("Microsoft Corporation develops software" in c for c in claims)
    assert any("automotive segment deliveries increased" in c for c in claims)
    # The raw table line with multiple pipes must NOT be extracted as a claim
    assert not any("Total automotive revenues | 82,419" in c for c in claims)
    assert not any("Col1 | Col2" in c for c in claims)


def test_claim_extractor_italicized_and_meta_placeholders():
    """Verify that italicized notices and fallback placeholders are filtered out."""
    extractor = ClaimExtractor()
    text = (
        "- Management Discussion [E5]: Operating expenses rose 12% in FY2023 [E5].\n"
        "_No comparative numerical data available for this section._\n"
        "_No specific risk factor excerpts identified in the target filings._\n"
    )
    result = extractor.extract_claims(text)
    assert len(result.claims) == 1
    assert "Operating expenses rose 12%" in result.claims[0].claim_text
    assert not any("comparative numerical data" in c.claim_text for c in result.claims)


def test_numeric_verifier_presentation_rounding_tolerance():
    """Verify NumericVerifier accepts presentation-rounded numbers (e.g. 0.22% vs 0.2229%)."""
    verifier = NumericVerifier()

    # Case 1: 0.22% presentation of 0.2229% (approx 1.3% relative diff, but exact under 2-decimal rounding)
    assert verifier.is_close_within_tolerance(0.22, 0.2229) is True

    # Case 2: 15.5 presentation of 15.52
    assert verifier.is_close_within_tolerance(15.5, 15.52) is True


def test_research_coordinator_section_normalization():
    """Verify ResearchCoordinator normalizes section IDs with underscores/hyphens."""
    coordinator = ResearchCoordinator()

    evidence_map = {
        "E1": {
            "citation_id": "E1",
            "section_identifier": "ITEM_1A",
            "text": "Risk factor disclosure regarding supply chain disruption and international tariffs.",
        },
        "E2": {
            "citation_id": "E2",
            "section_identifier": "ITEM_7",
            "text": "Management discussion of operations and historical cash flows during fiscal 2023.",
        },
        "E3": {
            "citation_id": "E3",
            "section_identifier": "ITEM_1",
            "text": "Business overview detailing corporate product segments and commercial footprint.",
        },
    }

    sections = coordinator.organize_section_findings(evidence_map, {}, [], [])

    assert any("[E1]" in item for item in sections["risk_factors"])
    assert any("[E2]" in item for item in sections["business_operations_mda"])
    assert any("[E3]" in item for item in sections["company_overview"])


def test_research_coordinator_strict_chunk_provenance():
    """Verify ResearchCoordinator rejects synthetic or untraceable chunk IDs."""
    coordinator = ResearchCoordinator()

    retrieved = [
        {"chunk_id": "valid_chunk_1", "text": "Valid text 1"},
        {"chunk_id": "synthetic_abc", "text": "Synthetic text 2"},
        {"text": "Missing chunk id entirely"},
    ]

    evidence_map, deduped = coordinator.build_evidence_map(retrieved, [])
    assert len(evidence_map) == 1
    assert "E1" in evidence_map
    assert evidence_map["E1"]["chunk_id"] == "valid_chunk_1"


def test_research_coordinator_word_boundary_truncation():
    """Verify organize_section_findings truncates at word boundaries to protect numbers."""
    coordinator = ResearchCoordinator()

    long_text = "Operating results were driven by strong enterprise demand where segment deliveries reached 26,519 units during the final quarter of the fiscal year."
    evidence_map = {
        "E1": {
            "citation_id": "E1",
            "section_identifier": "ITEM_7",
            "text": long_text,
        }
    }

    sections = coordinator.organize_section_findings(evidence_map, {}, [], [])
    assert len(sections["business_operations_mda"]) == 1
    mda_item = sections["business_operations_mda"][0]
    # Suffix must not cut off numbers like '26,'
    assert not mda_item.endswith("26, ...")
    assert "26,519" in mda_item


def test_report_agent_takeaway_grounding():
    """Verify ReportAgent grounds Section 7 key findings in genuine section citations."""
    agent = ReportAgent()

    sections = {
        "company_overview": ["Business summary [E1]: Core cloud infrastructure."],
        "financial_performance": ["Revenue reached $211.9B [C1]."],
        "historical_comparison": ["Revenue showed an expanding trend [C2]."],
        "business_operations_mda": ["Management noted margin expansion [E2]."],
        "risk_factors": ["Operational risks involve foreign exchange volatility [E3]."],
    }
    calc_map = {
        "C1": {
            "metric_name": "revenue",
            "calculated_value": 211915000000.0,
            "unit": "USD",
            "formula_name": "Revenue",
            "formula_expression": "Rev",
            "fiscal_year": 2023,
            "calculation_id": "calc_01",
        }
    }
    evidence_map = {
        "E1": {"citation_id": "E1", "section_identifier": "ITEM_1"},
        "E2": {"citation_id": "E2", "section_identifier": "ITEM_7"},
        "E3": {"citation_id": "E3", "section_identifier": "ITEM_1A"},
    }

    report_sections = agent.assemble_sections(
        company_name="Microsoft Corporation",
        ticker="MSFT",
        period="FY2023",
        question="Analyze financial results and operating margins.",
        section_findings=sections,
        calc_map=calc_map,
        evidence_map=evidence_map,
        comparisons=[],
        trends=[],
    )

    sec7 = next(s for s in report_sections if s.section_key == "key_findings")
    assert sec7 is not None
    assert "Synthesis of Core Evidence" in sec7.content_markdown
    # Grounding must include genuine citations
    assert "[E1]" in sec7.content_markdown
    assert "[C1]" in sec7.content_markdown
    assert "[E2]" in sec7.content_markdown
