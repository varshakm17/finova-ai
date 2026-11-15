"""Tests for CompanyService, ticker resolution, and caching."""

from pathlib import Path
from unittest.mock import MagicMock

from backend.data.company_service import CompanyService, normalize_ticker
from tests.fixtures.sec_mock_data import MOCK_TICKERS_PAYLOAD


def test_normalize_ticker() -> None:
    """Verify ticker normalization handles case, whitespace, and exchange dots."""
    assert normalize_ticker("aapl") == "AAPL"
    assert normalize_ticker("  msft  ") == "MSFT"
    assert normalize_ticker("brk.b") == "BRK-B"
    assert normalize_ticker("BF.A") == "BF-A"
    assert normalize_ticker("") == ""


def test_company_service_lookup_and_search(tmp_path: Path) -> None:
    """Verify company lookup by ticker and CIK using mocked SEC ticker payload."""
    mock_client = MagicMock()
    mock_client.get_company_tickers.return_value = MOCK_TICKERS_PAYLOAD

    cache_file = tmp_path / "company_tickers_test.json"
    service = CompanyService(sec_client=mock_client, cache_path=cache_file)

    # Validate Apple
    aapl = service.get_company_by_ticker("AAPL")
    assert aapl is not None
    assert aapl["ticker"] == "AAPL"
    assert aapl["cik"] == "0000320193"
    assert aapl["name"] == "Apple Inc."

    # Case insensitive lookup
    aapl_lower = service.get_company_by_ticker("aapl")
    assert aapl_lower == aapl

    # Validate Microsoft
    msft = service.get_company_by_ticker("MSFT")
    assert msft is not None
    assert msft["cik"] == "0000789019"

    # Validate NVIDIA
    nvda = service.get_company_by_ticker("NVDA")
    assert nvda is not None
    assert nvda["cik"] == "0001045810"

    # Validate CIK lookup
    by_cik = service.get_company_by_cik("0000320193")
    assert by_cik is not None
    assert by_cik["ticker"] == "AAPL"

    # Validate search
    search_results = service.search_companies("Apple")
    assert len(search_results) >= 1
    assert search_results[0]["ticker"] == "AAPL"

    # Validate non-existent ticker
    unknown = service.get_company_by_ticker("XYZNONEXISTENT")
    assert unknown is None

    # Check cache file was created on disk
    assert cache_file.exists()


def test_company_service_loads_from_cache(tmp_path: Path) -> None:
    """Verify company service uses existing cache without calling SEC client."""
    mock_client = MagicMock()
    cache_file = tmp_path / "cached_tickers.json"

    # Pre-populate cache file
    import json

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(MOCK_TICKERS_PAYLOAD, f)

    service = CompanyService(sec_client=mock_client, cache_path=cache_file)
    aapl = service.get_company_by_ticker("AAPL")

    assert aapl is not None
    assert aapl["ticker"] == "AAPL"
    mock_client.get_company_tickers.assert_not_called()
