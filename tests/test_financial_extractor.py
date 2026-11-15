"""Tests for FinancialExtractor and period classification."""

from backend.data.data_normalizer import (
    FinancialObservation,
    calculate_duration_days,
    classify_period_type,
    deduplicate_observations,
)
from backend.data.financial_extractor import FinancialExtractor
from tests.fixtures.sec_mock_data import MOCK_COMPANY_FACTS_PAYLOAD


def test_calculate_duration_days() -> None:
    """Verify ISO date duration calculation."""
    assert calculate_duration_days("2023-01-01", "2023-01-31") == 30
    assert calculate_duration_days("2022-10-01", "2023-09-30") == 364
    assert calculate_duration_days(None, "2023-09-30") is None
    assert calculate_duration_days("invalid", "dates") is None


def test_classify_period_type() -> None:
    """Verify period type accurately separates Annual, Quarterly, YTD, and Instant."""
    # Balance sheet instant
    assert (
        classify_period_type(
            is_instant=True, duration_days=None, form="10-K", fiscal_period="FY"
        )
        == "instant"
    )

    # Annual flow item (~365 days)
    assert (
        classify_period_type(
            is_instant=False, duration_days=364, form="10-K", fiscal_period="FY"
        )
        == "annual"
    )

    # Standalone quarter (~90 days)
    assert (
        classify_period_type(
            is_instant=False, duration_days=91, form="10-Q", fiscal_period="Q2"
        )
        == "quarterly"
    )

    # Year-To-Date (9 Months in 10-Q) - critical distinction
    assert (
        classify_period_type(
            is_instant=False, duration_days=273, form="10-Q", fiscal_period="Q3"
        )
        == "ytd"
    )


def test_extract_company_facts_metrics() -> None:
    """Verify extraction of standard canonical metrics from SEC XBRL company facts."""
    extractor = FinancialExtractor()
    observations = extractor.extract_company_facts(
        company_facts=MOCK_COMPANY_FACTS_PAYLOAD,
        ticker="AAPL",
        company_name="Apple Inc.",
    )

    assert len(observations) > 0

    metric_names = {obs.metric_name for obs in observations}
    assert "Revenue" in metric_names
    assert "Total Assets" in metric_names
    assert "Operating Income" in metric_names
    assert "Net Income" in metric_names
    assert "Operating Cash Flow" in metric_names
    assert "Capital Expenditures" in metric_names

    # Check Revenue annual observation
    revenue_annual = next(
        obs
        for obs in observations
        if obs.metric_name == "Revenue" and obs.period_type == "annual"
    )
    assert revenue_annual.numeric_value == 383285000000.0
    assert revenue_annual.fiscal_year == 2023
    assert revenue_annual.statement_type == "Income Statement"
    assert revenue_annual.unit == "USD"
    assert revenue_annual.company_ticker == "AAPL"

    # Check Revenue quarterly observation
    revenue_q3 = next(
        obs
        for obs in observations
        if obs.metric_name == "Revenue" and obs.period_type == "quarterly"
    )
    assert revenue_q3.numeric_value == 81797000000.0
    assert revenue_q3.fiscal_period == "Q3"

    # Check Balance Sheet instant observation
    assets = next(obs for obs in observations if obs.metric_name == "Total Assets")
    assert assets.period_type == "instant"
    assert assets.numeric_value == 352583000000.0
    assert assets.statement_type == "Balance Sheet"


def test_deduplicate_observations_prefers_amendments() -> None:
    """Verify that deduplication preserves the newer amendment filing for the same period."""
    base_obs = FinancialObservation(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        metric_name="Revenue",
        statement_type="Income Statement",
        original_tag="us-gaap:Revenues",
        numeric_value=100.0,
        unit="USD",
        period_start="2023-01-01",
        period_end="2023-12-31",
        duration_days=364,
        period_type="annual",
        fiscal_year=2023,
        fiscal_period="FY",
        filing_date="2024-01-15",
        filing_type="10-K",
        accession_number="0001-original",
        source_url="http://sec.gov/1",
    )

    amended_obs = FinancialObservation(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        metric_name="Revenue",
        statement_type="Income Statement",
        original_tag="us-gaap:Revenues",
        numeric_value=105.0,  # Restated value
        unit="USD",
        period_start="2023-01-01",
        period_end="2023-12-31",
        duration_days=364,
        period_type="annual",
        fiscal_year=2023,
        fiscal_period="FY",
        filing_date="2024-03-20",  # Later filing date
        filing_type="10-K/A",
        accession_number="0002-amended",
        source_url="http://sec.gov/2",
    )

    deduped = deduplicate_observations([base_obs, amended_obs])
    assert len(deduped) == 1
    assert deduped[0].numeric_value == 105.0
    assert deduped[0].filing_type == "10-K/A"
