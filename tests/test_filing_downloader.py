"""Tests for FilingDownloader, URL validation, and fair-access download policies."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.data.filing_downloader import (
    FilingDownloader,
    FilingSizeExceededError,
    InvalidSECUrlError,
    validate_sec_url,
)
from backend.data.sec_client import (
    SECAuthenticationError,
    SECNotFoundError,
    SECRateLimitError,
)
from config.settings import Settings


def test_validate_sec_url() -> None:
    """Verify that only approved official SEC domains are permitted."""
    validate_sec_url(
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl.htm"
    )
    validate_sec_url("https://data.sec.gov/submissions/CIK0000320193.json")

    # Insecure or unauthorized host
    with pytest.raises(InvalidSECUrlError, match="Unauthorized host"):
        validate_sec_url("https://malicious-site.com/edgar/file.htm")

    with pytest.raises(InvalidSECUrlError, match="Insecure or invalid URL scheme"):
        validate_sec_url("ftp://www.sec.gov/file.htm")

    with pytest.raises(InvalidSECUrlError, match="URL is empty"):
        validate_sec_url("")


def test_filing_downloader_success(tmp_path: Path) -> None:
    """Verify successful filing document download and disk persistence."""
    test_settings = Settings(
        SEC_USER_AGENT="FinovaTest/1.0 (tester@example.com)",
        FILINGS_STORAGE_DIR=str(tmp_path),
    )
    downloader = FilingDownloader(settings=test_settings, storage_dir=tmp_path)

    sample_content = b"<html><body>Sample 10-K Content</body></html>"

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = sample_content
        mock_resp.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_resp

        downloaded = downloader.download_filing(
            cik="0000320193",
            ticker="AAPL",
            accession_number="0000320193-23-000106",
            form="10-K",
            primary_document="aapl-20230930.htm",
            source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        )

        assert downloaded.file_size_bytes == len(sample_content)
        assert downloaded.is_cached is False
        assert downloaded.local_file_path.exists()
        assert downloaded.local_file_path.read_bytes() == sample_content

        # Subsequent call should return cached file without network call
        mock_get.reset_mock()
        cached = downloader.download_filing(
            cik="0000320193",
            ticker="AAPL",
            accession_number="0000320193-23-000106",
            form="10-K",
            primary_document="aapl-20230930.htm",
            source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        )
        assert cached.is_cached is True
        mock_get.assert_not_called()


def test_filing_downloader_size_exceeded(tmp_path: Path) -> None:
    """Verify FilingSizeExceededError is raised when document exceeds configured size limit."""
    downloader = FilingDownloader(
        settings=Settings(SEC_USER_AGENT="FinovaTest/1.0 (tester@example.com)"),
        storage_dir=tmp_path,
        max_size_bytes=100,  # 100 bytes limit
    )

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"A" * 500  # 500 bytes
        mock_resp.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_resp

        with pytest.raises(
            FilingSizeExceededError, match="exceeds configured maximum limit"
        ):
            downloader.download_filing(
                cik="0000320193",
                ticker="AAPL",
                accession_number="0000320193-23-000106",
                form="10-K",
                primary_document="aapl-20230930.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
            )


def test_filing_downloader_http_errors(tmp_path: Path) -> None:
    """Verify HTTP 403, 404, and 429 error mapping."""
    downloader = FilingDownloader(
        settings=Settings(SEC_USER_AGENT="FinovaTest/1.0 (tester@example.com)"),
        storage_dir=tmp_path,
        max_retries=1,
        backoff_factor=0.01,
    )

    # 404 Not Found
    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock(status_code=404)
        mock_get.return_value = mock_resp
        with pytest.raises(SECNotFoundError):
            downloader.download_filing(
                cik="0000320193",
                ticker="AAPL",
                accession_number="0000320193-23-000106",
                form="10-K",
                primary_document="aapl.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl.htm",
            )

    # 403 Forbidden
    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock(status_code=403)
        mock_get.return_value = mock_resp
        with pytest.raises(SECAuthenticationError):
            downloader.download_filing(
                cik="0000320193",
                ticker="AAPL",
                accession_number="0000320193-23-000106",
                form="10-K",
                primary_document="aapl.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl.htm",
            )

    # 429 Rate Limit
    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock(status_code=429)
        mock_get.return_value = mock_resp
        with pytest.raises(SECRateLimitError):
            downloader.download_filing(
                cik="0000320193",
                ticker="AAPL",
                accession_number="0000320193-23-000106",
                form="10-K",
                primary_document="aapl.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl.htm",
            )
