"""Tests for SQLite database schema, foreign keys, upserts, and querying."""

from backend.data.data_normalizer import FinancialObservation
from backend.data.storage import Database


def test_database_initialization() -> None:
    """Verify database schema creation in memory."""
    db = Database(db_path=":memory:")
    with db.connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "companies" in table_names
        assert "filings" in table_names
        assert "financial_observations" in table_names


def test_company_upsert_and_queries() -> None:
    """Verify company insert, update on conflict, and query functions."""
    db = Database(db_path=":memory:")

    db.save_company(
        {
            "cik": "0000320193",
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sic": "3571",
            "sic_description": "Electronic Computers",
            "fiscal_year_end": "0930",
            "state_location": "CA",
        }
    )

    by_ticker = db.get_company_by_ticker("AAPL")
    assert by_ticker is not None
    assert by_ticker["ticker"] == "AAPL"
    assert by_ticker["cik"] == "0000320193"
    assert by_ticker["sic"] == "3571"

    by_cik = db.get_company_by_cik("0000320193")
    assert by_cik is not None
    assert by_cik["name"] == "Apple Inc."

    # Test update on conflict
    db.save_company(
        {
            "cik": "0000320193",
            "ticker": "AAPL",
            "name": "Apple Inc. Updated",
        }
    )
    updated = db.get_company_by_ticker("AAPL")
    assert updated is not None
    assert updated["name"] == "Apple Inc. Updated"
    assert updated["sic"] == "3571"  # Retained COALESCE


def test_filings_upsert_and_queries() -> None:
    """Verify filings persistence, batch inserts, and form type filtering."""
    db = Database(db_path=":memory:")
    # Must save parent company first for foreign key constraint
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    filings = [
        {
            "accession_number": "0000320193-23-000106",
            "form": "10-K",
            "filing_date": "2023-11-03",
            "report_date": "2023-09-30",
            "is_xbrl": True,
            "url": "http://sec.gov/10k",
        },
        {
            "accession_number": "0000320193-23-000077",
            "form": "10-Q",
            "filing_date": "2023-08-04",
            "report_date": "2023-07-01",
            "is_xbrl": True,
            "url": "http://sec.gov/10q",
        },
    ]

    count = db.save_filings("0000320193", filings)
    assert count == 2

    # Query all filings
    all_filings = db.get_filings("0000320193")
    assert len(all_filings) == 2

    # Filter by 10-K
    k_filings = db.get_filings("0000320193", form_type="10-K")
    assert len(k_filings) == 1
    assert k_filings[0]["form"] == "10-K"


def test_observations_storage_and_filters() -> None:
    """Verify financial observations persistence and querying with year/metric filters."""
    db = Database(db_path=":memory:")
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})

    obs1 = FinancialObservation(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        metric_name="Revenue",
        statement_type="Income Statement",
        original_tag="us-gaap:Revenues",
        numeric_value=383285000000.0,
        unit="USD",
        period_start="2022-10-01",
        period_end="2023-09-30",
        duration_days=364,
        period_type="annual",
        fiscal_year=2023,
        fiscal_period="FY",
        filing_date="2023-11-03",
        filing_type="10-K",
        accession_number="0000320193-23-000106",
        source_url="http://sec.gov/1",
    )

    obs2 = FinancialObservation(
        company_ticker="AAPL",
        company_cik="0000320193",
        company_name="Apple Inc.",
        metric_name="Operating Income",
        statement_type="Income Statement",
        original_tag="us-gaap:OperatingIncomeLoss",
        numeric_value=114301000000.0,
        unit="USD",
        period_start="2022-10-01",
        period_end="2023-09-30",
        duration_days=364,
        period_type="annual",
        fiscal_year=2023,
        fiscal_period="FY",
        filing_date="2023-11-03",
        filing_type="10-K",
        accession_number="0000320193-23-000106",
        source_url="http://sec.gov/1",
    )

    saved = db.save_financial_observations([obs1, obs2])
    assert saved == 2

    # Query all
    results = db.get_financial_observations("AAPL")
    assert len(results) == 2

    # Filter by metric name
    rev_results = db.get_financial_observations("AAPL", metric_name="Revenue")
    assert len(rev_results) == 1
    assert rev_results[0].metric_name == "Revenue"

    # Filter by year
    fy2023 = db.get_financial_observations("AAPL", start_year=2023, end_year=2023)
    assert len(fy2023) == 2

    fy2022 = db.get_financial_observations("AAPL", start_year=2022, end_year=2022)
    assert len(fy2022) == 0

    # Test uniqueness: re-saving updated numeric value modifies without duplicate row
    obs1_updated = obs1.model_copy(update={"numeric_value": 390000000000.0})
    db.save_financial_observations([obs1_updated])

    post_update = db.get_financial_observations("AAPL", metric_name="Revenue")
    assert len(post_update) == 1
    assert post_update[0].numeric_value == 390000000000.0
