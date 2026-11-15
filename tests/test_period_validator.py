"""Unit tests for period and unit compatibility validator."""

from backend.data.data_normalizer import FinancialObservation
from backend.finance.period_validator import (
    find_opening_balance_observation,
    validate_flow_period_alignment,
    validate_instant_balance_sheet_alignment,
    validate_units,
)


def make_test_obs(
    metric_name: str,
    numeric_value: float,
    unit: str = "USD",
    period_start: str | None = "2022-10-01",
    period_end: str = "2023-09-30",
    period_type: str = "annual",
) -> FinancialObservation:
    """Helper creating FinancialObservation instances for unit tests."""
    return FinancialObservation(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        metric_name=metric_name,
        statement_type="Income Statement",
        original_tag=f"us-gaap:{metric_name}",
        numeric_value=numeric_value,
        unit=unit,
        period_start=period_start,
        period_end=period_end,
        period_type=period_type,
        filing_date="2023-11-03",
        filing_type="10-K",
        accession_number="0000320193-23-000106",
        source_url="https://sec.gov",
    )


def test_validate_units_matching() -> None:
    """Verify observations with consistent USD units pass validation."""
    obs1 = make_test_obs("Revenue", 1000.0, unit="USD")
    obs2 = make_test_obs("Gross Profit", 400.0, unit="USD")

    valid, err = validate_units([obs1, obs2], expected_unit="USD")
    assert valid is True
    assert err is None


def test_validate_units_mismatch() -> None:
    """Verify mixing incompatible units (e.g. USD and shares) is rejected."""
    obs1 = make_test_obs("Revenue", 1000.0, unit="USD")
    obs2 = make_test_obs("Common Shares", 500.0, unit="shares")

    valid, err = validate_units([obs1, obs2], expected_unit="USD")
    assert valid is False
    assert "Unit incompatibility" in err


def test_validate_units_unexpected_currency() -> None:
    """Verify non-expected currency unit is rejected."""
    obs1 = make_test_obs("Revenue", 1000.0, unit="EUR")

    valid, err = validate_units([obs1], expected_unit="USD")
    assert valid is False
    assert "Unexpected unit 'EUR'" in err


def test_validate_flow_period_alignment_matching() -> None:
    """Verify flow items sharing identical period type and dates pass."""
    rev = make_test_obs(
        "Revenue", 1000.0, period_type="annual", period_end="2023-09-30"
    )
    gp = make_test_obs(
        "Gross Profit", 400.0, period_type="annual", period_end="2023-09-30"
    )

    valid, err = validate_flow_period_alignment(rev, gp)
    assert valid is True
    assert err is None


def test_validate_flow_period_alignment_type_mismatch() -> None:
    """Verify annual vs quarterly period types are rejected."""
    rev_annual = make_test_obs("Revenue", 1000.0, period_type="annual")
    rev_quarterly = make_test_obs("Revenue", 250.0, period_type="quarterly")

    valid, err = validate_flow_period_alignment(rev_annual, rev_quarterly)
    assert valid is False
    assert "Period type mismatch" in err


def test_validate_flow_period_alignment_ytd_rejection() -> None:
    """Verify cumulative YTD periods cannot be combined with periodic metrics."""
    rev_ytd = make_test_obs("Revenue", 600.0, period_type="ytd")
    gp_ytd = make_test_obs("Gross Profit", 250.0, period_type="ytd")

    valid, err = validate_flow_period_alignment(rev_ytd, gp_ytd)
    assert valid is False
    assert "Year-To-Date (YTD)" in err


def test_validate_flow_period_alignment_date_mismatch() -> None:
    """Verify mismatching period end dates are rejected."""
    rev_2023 = make_test_obs("Revenue", 1000.0, period_end="2023-09-30")
    gp_2022 = make_test_obs("Gross Profit", 400.0, period_end="2022-09-30")

    valid, err = validate_flow_period_alignment(rev_2023, gp_2022)
    assert valid is False
    assert "Period end date mismatch" in err


def test_validate_instant_balance_sheet_alignment() -> None:
    """Verify balance sheet instant observation alignment with target income statement date."""
    bs_exact = make_test_obs(
        "Current Assets", 500.0, period_end="2023-09-30", period_type="instant"
    )
    valid, _ = validate_instant_balance_sheet_alignment(bs_exact, "2023-09-30")
    assert valid is True

    # Floating fiscal calendar within 7-day tolerance (e.g. Saturday Sep 24 vs Sep 30)
    bs_floating = make_test_obs(
        "Current Assets", 500.0, period_end="2023-09-24", period_type="instant"
    )
    valid_float, _ = validate_instant_balance_sheet_alignment(
        bs_floating, "2023-09-30", tolerance_days=7
    )
    assert valid_float is True

    # Date discrepancy beyond tolerance (e.g. 60 days)
    bs_old = make_test_obs(
        "Current Assets", 500.0, period_end="2023-06-30", period_type="instant"
    )
    valid_old, err_old = validate_instant_balance_sheet_alignment(
        bs_old, "2023-09-30", tolerance_days=7
    )
    assert valid_old is False
    assert "Date discrepancy" in err_old


def test_find_opening_balance_observation() -> None:
    """Verify opening balance sheet observation matching for ROA/ROE."""
    candidates = [
        make_test_obs(
            "Total Assets", 900.0, period_end="2022-09-24", period_type="instant"
        ),
        make_test_obs(
            "Total Assets", 1100.0, period_end="2023-09-30", period_type="instant"
        ),
    ]

    # Target opening date: 2022-09-25 (Apple FY 2023 period_start)
    match = find_opening_balance_observation(
        metric_name="Total Assets",
        closing_period_start="2022-09-25",
        candidate_observations=candidates,
        tolerance_days=7,
    )
    assert match is not None
    assert match.numeric_value == 900.0

    # Missing opening balance
    no_match = find_opening_balance_observation(
        metric_name="Total Assets",
        closing_period_start="2020-09-25",
        candidate_observations=candidates,
        tolerance_days=7,
    )
    assert no_match is None


def test_validator_edge_cases() -> None:
    """Verify edge cases: empty unit lists, invalid dates, and non-instant period types."""
    # Empty unit list
    valid, err = validate_units([])
    assert valid is True
    assert err is None

    # Instant balance sheet alignment with non-instant type
    non_instant = make_test_obs("Current Assets", 100.0, period_type="annual")
    valid, err = validate_instant_balance_sheet_alignment(non_instant, "2023-09-30")
    assert valid is False
    assert "must have period_type 'instant'" in err

    # Instant balance sheet alignment with invalid date format
    bad_date_obs = make_test_obs(
        "Current Assets", 100.0, period_end="invalid-date", period_type="instant"
    )
    valid, err = validate_instant_balance_sheet_alignment(bad_date_obs, "2023-09-30")
    assert valid is False
    assert "Invalid date formatting" in err

    # find_opening_balance_observation with None period start
    assert find_opening_balance_observation("Total Assets", None, []) is None

    # find_opening_balance_observation with invalid period start date
    assert find_opening_balance_observation("Total Assets", "not-a-date", []) is None

    # find_opening_balance_observation with candidate having invalid date
    bad_candidate = make_test_obs(
        "Total Assets", 100.0, period_end="corrupted", period_type="instant"
    )
    assert (
        find_opening_balance_observation("Total Assets", "2023-09-30", [bad_candidate])
        is None
    )
