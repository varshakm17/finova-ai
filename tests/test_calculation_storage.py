"""Unit tests for financial calculations storage in SQLite."""

from backend.data.data_normalizer import FinancialObservation
from backend.data.storage import Database


def get_test_db() -> Database:
    """Create an in-memory SQLite database initialized with company seed."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})
    return db


def test_save_and_get_financial_calculations() -> None:
    """Verify calculation records can be saved, filtered, and retrieved."""
    db = get_test_db()

    records = [
        {
            "calculation_id": "0000320193_gross_profit_margin_annual_2023-09-30",
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "period_type": "annual",
            "period_start": "2022-10-01",
            "period_end": "2023-09-30",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "formula_name": "Gross Profit Margin",
            "formula_expression": "(Gross Profit / Revenue) * 100",
            "calculation_status": "calculated",
            "unavailable_reason": None,
            "input_observations": [
                {"metric_name": "Gross Profit", "value": 169148000000.0, "unit": "USD"},
                {"metric_name": "Revenue", "value": 383285000000.0, "unit": "USD"},
            ],
            "warnings": [],
        },
        {
            "calculation_id": "0000320193_net_profit_margin_annual_2023-09-30",
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "metric_name": "net_profit_margin",
            "calculated_value": 25.31,
            "unit": "percentage",
            "period_type": "annual",
            "period_start": "2022-10-01",
            "period_end": "2023-09-30",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "formula_name": "Net Profit Margin",
            "formula_expression": "(Net Income / Revenue) * 100",
            "calculation_status": "calculated",
            "unavailable_reason": None,
            "input_observations": [
                {"metric_name": "Net Income", "value": 96995000000.0, "unit": "USD"},
                {"metric_name": "Revenue", "value": 383285000000.0, "unit": "USD"},
            ],
            "warnings": [],
        },
        {
            "calculation_id": "0000320193_debt_to_equity_ratio_annual_2023-09-30",
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "metric_name": "debt_to_equity_ratio",
            "calculated_value": None,
            "unit": "ratio",
            "period_type": "annual",
            "period_start": "",
            "period_end": "2023-09-30",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "formula_name": "Debt to Equity Ratio",
            "formula_expression": "Total Debt / Stockholders' Equity",
            "calculation_status": "unavailable",
            "unavailable_reason": "Total Debt observation is not reported in statutory XBRL facts.",
            "input_observations": [],
            "warnings": [],
        },
    ]

    saved_count = db.save_financial_calculations(records)
    assert saved_count == 3

    # Fetch all for AAPL
    all_calcs = db.get_financial_calculations("AAPL")
    assert len(all_calcs) == 3

    # Filter by metric_name
    gp_calcs = db.get_financial_calculations("AAPL", metric_name="gross_profit_margin")
    assert len(gp_calcs) == 1
    assert gp_calcs[0]["metric_name"] == "gross_profit_margin"
    assert gp_calcs[0]["calculated_value"] == 44.13
    assert len(gp_calcs[0]["inputs"]) == 2

    # Filter by period_type
    annual_calcs = db.get_financial_calculations("AAPL", period_type="annual")
    assert len(annual_calcs) == 3

    # Filter by year
    year_calcs = db.get_financial_calculations("AAPL", start_year=2023, end_year=2023)
    assert len(year_calcs) == 3


def test_get_financial_calculation_by_id() -> None:
    """Verify single calculation receipt retrieval by ID with inputs and warnings."""
    db = get_test_db()
    calc_id = "0000320193_free_cash_flow_annual_2023-09-30"

    db.save_financial_calculations(
        [
            {
                "calculation_id": calc_id,
                "cik": "0000320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "metric_name": "free_cash_flow",
                "calculated_value": 99584000000.0,
                "unit": "USD",
                "period_type": "annual",
                "period_start": "2022-10-01",
                "period_end": "2023-09-30",
                "fiscal_year": 2023,
                "fiscal_period": "FY",
                "formula_name": "Free Cash Flow",
                "formula_expression": "Operating Cash Flow - Normalized CapEx",
                "calculation_status": "calculated",
                "unavailable_reason": None,
                "input_observations": [
                    {
                        "metric_name": "Operating Cash Flow",
                        "value": 110543000000.0,
                        "unit": "USD",
                    },
                    {
                        "metric_name": "Capital Expenditures",
                        "value": 10959000000.0,
                        "unit": "USD",
                    },
                ],
                "warnings": ["CapEx normalized to positive cash outflow magnitude"],
            }
        ]
    )

    receipt = db.get_financial_calculation_by_id(calc_id)
    assert receipt is not None
    assert receipt["calculation_id"] == calc_id
    assert receipt["calculated_value"] == 99584000000.0
    assert len(receipt["inputs"]) == 2
    assert len(receipt["warnings"]) == 1

    # Non-existent ID returns None
    assert db.get_financial_calculation_by_id("non-existent-id") is None


def test_recalculation_upsert_behavior() -> None:
    """Verify recalculation safely updates existing records without duplicate key errors."""
    db = get_test_db()
    calc_id = "0000320193_gross_profit_margin_annual_2023-09-30"

    initial = {
        "calculation_id": calc_id,
        "cik": "0000320193",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "metric_name": "gross_profit_margin",
        "calculated_value": 44.0,
        "unit": "percentage",
        "period_type": "annual",
        "period_start": "2022-10-01",
        "period_end": "2023-09-30",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "formula_name": "Gross Profit Margin",
        "formula_expression": "(Gross Profit / Revenue) * 100",
        "calculation_status": "calculated",
        "unavailable_reason": None,
        "input_observations": [],
        "warnings": [],
    }
    db.save_financial_calculations([initial])

    # Recalculated with updated value
    updated = dict(initial)
    updated["calculated_value"] = 44.13
    updated["unavailable_reason"] = None
    db.save_financial_calculations([updated])

    calcs = db.get_financial_calculations("AAPL", metric_name="gross_profit_margin")
    assert len(calcs) == 1
    assert calcs[0]["calculated_value"] == 44.13


def test_reported_observations_remain_untouched() -> None:
    """Verify calculations table does not alter or overwrite reported SEC observations."""
    db = get_test_db()
    # Save a raw observation
    db.save_financial_observations(
        [
            FinancialObservation(
                company_cik="0000320193",
                company_ticker="AAPL",
                company_name="Apple Inc.",
                metric_name="Revenue",
                statement_type="Income Statement",
                original_tag="us-gaap:Revenues",
                numeric_value=383285000000.0,
                unit="USD",
                period_start="2022-10-01",
                period_end="2023-09-30",
                duration_days=365,
                period_type="annual",
                fiscal_year=2023,
                fiscal_period="FY",
                filing_date="2023-11-03",
                filing_type="10-K",
                accession_number="0000320193-23-000106",
                source_url="https://sec.gov",
            )
        ]
    )

    # Save a calculated metric
    db.save_financial_calculations(
        [
            {
                "calculation_id": "0000320193_revenue_growth_annual_2023-09-30",
                "cik": "0000320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "metric_name": "revenue_growth",
                "calculated_value": -2.8,
                "unit": "percentage",
                "period_type": "annual",
                "period_start": "2022-10-01",
                "period_end": "2023-09-30",
                "fiscal_year": 2023,
                "fiscal_period": "FY",
                "formula_name": "Revenue Growth",
                "formula_expression": "((Current - Previous) / Previous) * 100",
                "calculation_status": "calculated",
                "unavailable_reason": None,
                "input_observations": [],
                "warnings": [],
            }
        ]
    )

    # Verify reported observation is completely unchanged
    raw_obs = db.get_financial_observations("AAPL", metric_name="Revenue")
    assert len(raw_obs) == 1
    assert raw_obs[0].numeric_value == 383285000000.0
    assert raw_obs[0].metric_name == "Revenue"
