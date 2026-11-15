"""Integration tests for CalculationService."""

import pytest

from backend.data.data_normalizer import FinancialObservation
from backend.data.storage import Database
from backend.finance.calculation_service import CalculationService


def seed_synthetic_company_data(db: Database) -> None:
    """Seed synthetic AAPL multi-year financial observations into SQLite."""
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    obs = [
        # --- FY 2022 ---
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Revenue",
            statement_type="Income Statement",
            original_tag="us-gaap:Revenues",
            numeric_value=394328000000.0,
            unit="USD",
            period_start="2021-09-26",
            period_end="2022-09-24",
            period_type="annual",
            fiscal_year=2022,
            fiscal_period="FY",
            filing_date="2022-10-28",
            filing_type="10-K",
            accession_number="0000320193-22-000108",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Total Assets",
            statement_type="Balance Sheet",
            original_tag="us-gaap:Assets",
            numeric_value=352755000000.0,
            unit="USD",
            period_end="2022-09-24",
            period_type="instant",
            fiscal_year=2022,
            fiscal_period="FY",
            filing_date="2022-10-28",
            filing_type="10-K",
            accession_number="0000320193-22-000108",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Stockholders' Equity",
            statement_type="Balance Sheet",
            original_tag="us-gaap:StockholdersEquity",
            numeric_value=50672000000.0,
            unit="USD",
            period_end="2022-09-24",
            period_type="instant",
            fiscal_year=2022,
            fiscal_period="FY",
            filing_date="2022-10-28",
            filing_type="10-K",
            accession_number="0000320193-22-000108",
            source_url="https://sec.gov",
        ),
        # --- FY 2023 ---
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Revenue",
            statement_type="Income Statement",
            original_tag="us-gaap:Revenues",
            numeric_value=383285000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Gross Profit",
            statement_type="Income Statement",
            original_tag="us-gaap:GrossProfit",
            numeric_value=169148000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Operating Income",
            statement_type="Income Statement",
            original_tag="us-gaap:OperatingIncomeLoss",
            numeric_value=114301000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Net Income",
            statement_type="Income Statement",
            original_tag="us-gaap:NetIncomeLoss",
            numeric_value=96995000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Current Assets",
            statement_type="Balance Sheet",
            original_tag="us-gaap:AssetsCurrent",
            numeric_value=143566000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Current Liabilities",
            statement_type="Balance Sheet",
            original_tag="us-gaap:LiabilitiesCurrent",
            numeric_value=145308000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Total Assets",
            statement_type="Balance Sheet",
            original_tag="us-gaap:Assets",
            numeric_value=352583000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Stockholders' Equity",
            statement_type="Balance Sheet",
            original_tag="us-gaap:StockholdersEquity",
            numeric_value=62146000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Long-Term Debt",
            statement_type="Balance Sheet",
            original_tag="us-gaap:LongTermDebtNoncurrent",
            numeric_value=95281000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Operating Cash Flow",
            statement_type="Cash Flow Statement",
            original_tag="us-gaap:NetCashProvidedByUsedInOperatingActivities",
            numeric_value=110543000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Capital Expenditures",
            statement_type="Cash Flow Statement",
            original_tag="us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
            numeric_value=10959000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
    ]
    db.save_financial_observations(obs)


def test_calculation_service_full_suite() -> None:
    """Verify all 10 canonical financial metrics are computed or marked unavailable as specified."""
    db = Database(db_path=":memory:")
    seed_synthetic_company_data(db)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(
        ticker="AAPL",
        start_year=2023,
        end_year=2023,
        period_type="annual",
    )

    assert summary.ticker == "AAPL"
    assert summary.total_calculated > 0
    res_map = {
        r.metric_name: r for r in summary.calculations if r.period_end == "2023-09-30"
    }

    # 1. Revenue Growth: FY 2023 ($383.285B) vs FY 2022 ($394.328B) -> ~ -2.7999%
    rev_growth = res_map["revenue_growth"]
    assert rev_growth.status == "calculated"
    assert rev_growth.calculated_value == pytest.approx(-2.8005, rel=1e-3)
    assert len(rev_growth.inputs) == 2

    # 2. Gross Profit Margin: 169.148 / 383.285 * 100 -> ~ 44.13%
    gpm = res_map["gross_profit_margin"]
    assert gpm.status == "calculated"
    assert gpm.calculated_value == pytest.approx(44.1311, rel=1e-3)

    # 3. Operating Profit Margin: 114.301 / 383.285 * 100 -> ~ 29.82%
    opm = res_map["operating_profit_margin"]
    assert opm.status == "calculated"
    assert opm.calculated_value == pytest.approx(29.8214, rel=1e-3)

    # 4. Net Profit Margin: 96.995 / 383.285 * 100 -> ~ 25.31%
    npm = res_map["net_profit_margin"]
    assert npm.status == "calculated"
    assert npm.calculated_value == pytest.approx(25.3062, rel=1e-3)

    # 5. Current Ratio: 143.566 / 145.308 -> ~ 0.9880
    cr = res_map["current_ratio"]
    assert cr.status == "calculated"
    assert cr.calculated_value == pytest.approx(0.9880, rel=1e-3)

    # 6. Debt-to-Equity Ratio: Total Debt is NOT reported -> must be UNAVAILABLE
    de = res_map["debt_to_equity_ratio"]
    assert de.status == "unavailable"
    assert "Total Debt observation is not reported" in de.unavailable_reason
    assert de.calculated_value is None

    # Long-Term Debt to Equity: Long-Term Debt ($95.281B) / Equity ($62.146B) -> ~ 1.5332
    lt_de = res_map["long_term_debt_to_equity"]
    assert lt_de.status == "calculated"
    assert lt_de.calculated_value == pytest.approx(1.5332, rel=1e-3)

    # 7. Return on Assets (ROA): Net Income ($96.995B) / Avg Assets (($352.755B + $352.583B) / 2) * 100 -> ~ 27.50%
    roa = res_map["return_on_assets"]
    assert roa.status == "calculated"
    assert roa.calculated_value == pytest.approx(27.5022, rel=1e-3)
    assert len(roa.inputs) == 3  # Net Income, Opening Assets, Closing Assets

    # 8. Return on Equity (ROE): Net Income ($96.995B) / Avg Equity (($50.672B + $62.146B) / 2) * 100 -> ~ 171.95%
    roe = res_map["return_on_equity"]
    assert roe.status == "calculated"
    assert roe.calculated_value == pytest.approx(171.949, rel=1e-3)
    assert len(roe.inputs) == 3

    # 9. Operating Cash Flow Margin: 110.543 / 383.285 * 100 -> ~ 28.84%
    ocfm = res_map["operating_cash_flow_margin"]
    assert ocfm.status == "calculated"
    assert ocfm.calculated_value == pytest.approx(28.8409, rel=1e-3)

    # 10. Free Cash Flow: OCF ($110.543B) - CapEx ($10.959B) -> $99.584B
    fcf = res_map["free_cash_flow"]
    assert fcf.status == "calculated"
    assert fcf.calculated_value == pytest.approx(99584000000.0, rel=1e-3)
    assert len(fcf.warnings) == 1
    assert "Normalized CapEx" in fcf.warnings[0]


def test_calculation_service_missing_opening_balance() -> None:
    """Verify ROA/ROE return unavailable with clear rationale when opening balance sheet is missing."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    # Only FY 2023 data, NO prior year (2022) balance sheet
    obs = [
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Net Income",
            statement_type="Income Statement",
            original_tag="us-gaap:NetIncomeLoss",
            numeric_value=96995000000.0,
            unit="USD",
            period_start="2022-09-25",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Total Assets",
            statement_type="Balance Sheet",
            original_tag="us-gaap:Assets",
            numeric_value=352583000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
    ]
    db.save_financial_observations(obs)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(
        ticker="AAPL", metrics=["return_on_assets"]
    )
    roa = summary.calculations[0]

    assert roa.status == "unavailable"
    assert (
        "Opening balance sheet observation for Total Assets" in roa.unavailable_reason
    )
    assert (
        "cannot compute average total assets without fabricating data"
        in roa.unavailable_reason
    )


def test_calculation_service_unknown_company() -> None:
    """Verify unknown company raises ValueError."""
    db = Database(db_path=":memory:")
    service = CalculationService(db=db)

    with pytest.raises(ValueError, match="Company with ticker 'UNKNOWN' not found"):
        service.calculate_company_metrics(ticker="UNKNOWN")


def test_calculation_service_zero_revenue_denominator() -> None:
    """Verify zero revenue produces status 'invalid_inputs' without unhandled ZeroDivisionError."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    obs = [
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Revenue",
            statement_type="Income Statement",
            original_tag="us-gaap:Revenues",
            numeric_value=0.0,
            unit="USD",
            period_start="2022-10-01",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Gross Profit",
            statement_type="Income Statement",
            original_tag="us-gaap:GrossProfit",
            numeric_value=50000000.0,
            unit="USD",
            period_start="2022-10-01",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
    ]
    db.save_financial_observations(obs)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(
        ticker="AAPL", metrics=["gross_profit_margin"]
    )
    assert len(summary.calculations) == 1
    gpm = summary.calculations[0]
    assert gpm.status == "invalid_inputs"
    assert "Revenue is zero" in gpm.unavailable_reason


def test_calculation_service_total_debt_calculation() -> None:
    """Verify that when Total Debt is present, debt_to_equity_ratio calculates properly."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    obs = [
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Total Debt",
            statement_type="Balance Sheet",
            original_tag="us-gaap:DebtInstrumentCarryingAmount",
            numeric_value=120000000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Stockholders' Equity",
            statement_type="Balance Sheet",
            original_tag="us-gaap:StockholdersEquity",
            numeric_value=60000000000.0,
            unit="USD",
            period_end="2023-09-30",
            period_type="instant",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        ),
    ]
    db.save_financial_observations(obs)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(
        ticker="AAPL", metrics=["debt_to_equity_ratio"]
    )
    de = summary.calculations[0]
    assert de.status == "calculated"
    assert de.calculated_value == pytest.approx(2.0, rel=1e-3)


def test_calculation_service_quarterly_flow() -> None:
    """Verify quarterly metrics computation for Q3 flow observations."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    obs = [
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Revenue",
            statement_type="Income Statement",
            original_tag="us-gaap:Revenues",
            numeric_value=81800000000.0,
            unit="USD",
            period_start="2023-04-02",
            period_end="2023-07-01",
            duration_days=91,
            period_type="quarterly",
            fiscal_year=2023,
            fiscal_period="Q3",
            filing_date="2023-08-04",
            filing_type="10-Q",
            accession_number="0000320193-23-000077",
            source_url="https://sec.gov",
        ),
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Operating Income",
            statement_type="Income Statement",
            original_tag="us-gaap:OperatingIncomeLoss",
            numeric_value=23000000000.0,
            unit="USD",
            period_start="2023-04-02",
            period_end="2023-07-01",
            duration_days=91,
            period_type="quarterly",
            fiscal_year=2023,
            fiscal_period="Q3",
            filing_date="2023-08-04",
            filing_type="10-Q",
            accession_number="0000320193-23-000077",
            source_url="https://sec.gov",
        ),
    ]
    db.save_financial_observations(obs)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(
        ticker="AAPL", period_type="quarterly", metrics=["operating_profit_margin"]
    )
    assert summary.total_calculated == 1
    opm = summary.calculations[0]
    assert opm.status == "calculated"
    assert opm.period_type == "quarterly"
    assert opm.calculated_value == pytest.approx(28.1173, rel=1e-3)


def test_calculation_service_missing_inputs_mark_unavailable() -> None:
    """Verify that when expected input observations are missing, metrics return unavailable status."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    # Only single revenue observation: no prior revenue, no GP, no OPM, no NI, no balance sheet, no cash flow
    obs = [
        FinancialObservation(
            company_cik="0000320193",
            company_ticker="AAPL",
            company_name="Apple Inc.",
            metric_name="Revenue",
            statement_type="Income Statement",
            original_tag="us-gaap:Revenues",
            numeric_value=100000.0,
            unit="USD",
            period_start="2022-10-01",
            period_end="2023-09-30",
            period_type="annual",
            fiscal_year=2023,
            fiscal_period="FY",
            filing_date="2023-11-03",
            filing_type="10-K",
            accession_number="0000320193-23-000106",
            source_url="https://sec.gov",
        )
    ]
    db.save_financial_observations(obs)

    service = CalculationService(db=db)
    summary = service.calculate_company_metrics(ticker="AAPL")

    # All metrics should be unavailable because dependencies are absent
    for calc in summary.calculations:
        assert calc.status == "unavailable"
        assert calc.unavailable_reason is not None
