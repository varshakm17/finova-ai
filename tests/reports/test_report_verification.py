"""Tests for Report Anti-Hallucination Verification (Session 11).

Validates that claim-level verification operates correctly on multi-section
reports, verifying numerical values, dates, and citations against statutory evidence.
"""

from __future__ import annotations

import pytest

from backend.agents.verification_agent import VerificationAgent


@pytest.fixture
def verification_agent() -> VerificationAgent:
    return VerificationAgent()


def test_verify_report_valid_claims(verification_agent: VerificationAgent) -> None:
    """Test verification passes when report numbers exactly match calculation receipts."""
    report_data = {
        "report_id": "rep_test_01",
        "title": "Financial Research Brief: Apple Inc. (AAPL)",
        "markdown_content": (
            "# Financial Report: Apple Inc.\n\n"
            "In fiscal year 2023, Apple achieved a gross profit margin of 44.13% [C1]. "
            "Total services revenue expanded significantly across the period [E1]."
        ),
        "sections": [
            {
                "section_key": "financial_performance",
                "verification_status": "UNVERIFIED",
            }
        ],
        "metadata": {"verification_status": "UNVERIFIED"},
        "status": "completed",
    }
    evidence = [
        {
            "chunk_id": "e1",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "text": "Total services revenue expanded significantly across the period.",
            "section_identifier": "ITEM_7",
            "filing_date": "2023-11-03",
        }
    ]
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "fiscal_year": 2023,
            "period_end": "2023-09-30",
        }
    ]

    audit = verification_agent.verify_report(
        report_data=report_data,
        evidence=evidence,
        receipts=receipts,
    )

    assert audit["is_valid"] is True
    assert "REJECTED" not in audit["overall_status"]
    assert report_data["verification_status"] != "REJECTED"
    assert report_data["sections"][0]["verification_status"] != "REJECTED"


def test_verify_report_flags_hallucinated_number(
    verification_agent: VerificationAgent,
) -> None:
    """Test verification rejects report containing unsupported or inaccurate financial metrics."""
    report_data = {
        "report_id": "rep_test_02",
        "title": "Financial Research Brief: Apple Inc. (AAPL)",
        "markdown_content": (
            "# Financial Report: Apple Inc.\n\n"
            "In fiscal year 2023, Apple achieved a gross profit margin of 78.50% [C1]."
        ),
        "sections": [
            {
                "section_key": "financial_performance",
                "verification_status": "UNVERIFIED",
            }
        ],
        "metadata": {"verification_status": "UNVERIFIED"},
        "status": "completed",
    }
    evidence = []
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,  # Discrepancy: 78.50% vs 44.13%
            "unit": "percentage",
            "fiscal_year": 2023,
            "period_end": "2023-09-30",
        }
    ]

    audit = verification_agent.verify_report(
        report_data=report_data,
        evidence=evidence,
        receipts=receipts,
    )

    # Inaccurate number results in rejection
    assert audit["unsupported_claims"] > 0 or audit["contradicted_claims"] > 0
    assert audit["is_valid"] is False
    assert report_data["verification_status"].upper() == "REJECTED"
    assert report_data["status"] == "REJECTED"
