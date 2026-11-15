"""Tests for the SECClient, CIK normalization, and SEC policy compliance."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.data.sec_client import (
    SECAuthenticationError,
    SECClient,
    SECConfigurationError,
    SECNotFoundError,
    SECRateLimitError,
    normalize_cik,
    validate_user_agent,
)
from config.settings import Settings
from tests.fixtures.sec_mock_data import MOCK_SUBMISSIONS_PAYLOAD, MOCK_TICKERS_PAYLOAD


def test_normalize_cik() -> None:
    """Test CIK formatting across various valid integer and string representations."""
    assert normalize_cik(320193) == "0000320193"
    assert normalize_cik("320193") == "0000320193"
    assert normalize_cik("0000320193") == "0000320193"
    assert normalize_cik("CIK0000320193") == "0000320193"
    assert normalize_cik(" 789019 ") == "0000789019"

    with pytest.raises(ValueError):
        normalize_cik("invalid-cik")


def test_validate_user_agent() -> None:
    """Test validation of SEC User-Agent header compliance."""
    # Valid User-Agent containing application name and contact email
    validate_user_agent("FinovaAI-Research/0.1.0 (contact@example.com)")
    validate_user_agent("AcmeCorp Financial Data research-lead@acme.org")

    # Missing / empty
    with pytest.raises(SECConfigurationError, match="SEC_USER_AGENT is not configured"):
        validate_user_agent("")

    with pytest.raises(SECConfigurationError, match="SEC_USER_AGENT is not configured"):
        validate_user_agent(None)

    # Missing email
    with pytest.raises(
        SECConfigurationError, match="does not contain a valid contact email"
    ):
        validate_user_agent("FinovaAI Generic Bot")


def test_sec_client_get_company_tickers_mocked() -> None:
    """Verify SECClient.get_company_tickers with mocked HTTP 200 response."""
    test_settings = Settings(
        SEC_USER_AGENT="TestApp/1.0 (tester@example.com)",
    )
    client = SECClient(settings=test_settings)

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_TICKERS_PAYLOAD
        mock_get.return_value = mock_resp

        result = client.get_company_tickers()
        assert "0" in result
        assert result["0"]["ticker"] == "AAPL"


def test_sec_client_404_not_found() -> None:
    """Verify SECClient raises SECNotFoundError on HTTP 404."""
    test_settings = Settings(
        SEC_USER_AGENT="TestApp/1.0 (tester@example.com)",
    )
    client = SECClient(settings=test_settings)

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(SECNotFoundError):
            client.get_company_submissions("0000000000")


def test_sec_client_403_forbidden() -> None:
    """Verify SECClient raises SECAuthenticationError on HTTP 403."""
    test_settings = Settings(
        SEC_USER_AGENT="TestApp/1.0 (tester@example.com)",
    )
    client = SECClient(settings=test_settings)

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        with pytest.raises(SECAuthenticationError):
            client.get_company_facts("0000320193")


def test_sec_client_429_rate_limit_exceeded() -> None:
    """Verify SECClient retries and ultimately raises SECRateLimitError on persistent 429."""
    test_settings = Settings(
        SEC_USER_AGENT="TestApp/1.0 (tester@example.com)",
    )
    client = SECClient(settings=test_settings, max_retries=1, backoff_factor=0.01)

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        with pytest.raises(SECRateLimitError):
            client.get_company_facts("0000320193")


def test_sec_client_get_company_filings_flattening_and_filtering() -> None:
    """Verify column-oriented SEC filings data is correctly flattened and filtered."""
    test_settings = Settings(
        SEC_USER_AGENT="TestApp/1.0 (tester@example.com)",
    )
    client = SECClient(settings=test_settings)

    with patch.object(client, "get_company_submissions") as mock_subs:
        mock_subs.return_value = MOCK_SUBMISSIONS_PAYLOAD

        # Test all filings
        all_filings = client.get_company_filings("0000320193")
        assert len(all_filings) == 3
        assert all_filings[0]["accession_number"] == "0000320193-23-000106"
        assert all_filings[0]["form"] == "10-K"
        assert (
            "Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
            in all_filings[0]["url"]
        )

        # Test filtering by form
        k_filings = client.get_company_filings("0000320193", form_type="10-K")
        assert len(k_filings) == 1
        assert k_filings[0]["form"] == "10-K"

        q_filings = client.get_company_filings("0000320193", form_type="10-Q")
        assert len(q_filings) == 2
