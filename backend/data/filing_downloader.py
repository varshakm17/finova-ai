"""SEC Primary Filing Downloader.

Downloads official primary filing HTML documents from SEC EDGAR archives
with strict host validation, size limits, and fair-access throttling.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from backend.data.sec_client import (
    SECAuthenticationError,
    SECNetworkError,
    SECNotFoundError,
    SECRateLimitError,
    normalize_cik,
    validate_user_agent,
)
from backend.utils.logger import get_logger
from config.settings import BASE_DIR, Settings, get_settings

logger = get_logger("filing_downloader")

ALLOWED_SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "sec.gov"}


class FilingDownloadError(Exception):
    """Base exception for filing download operations."""


class FilingSizeExceededError(FilingDownloadError):
    """Raised when an SEC document exceeds the configured maximum byte limit."""


class InvalidSECUrlError(FilingDownloadError):
    """Raised when a download URL does not point to an approved SEC domain."""


@dataclass
class DownloadedFiling:
    """Metadata describing a successfully downloaded and validated SEC filing."""

    accession_number: str
    cik: str
    ticker: str
    form: str
    primary_document: str
    source_url: str
    local_file_path: Path
    document_hash: str
    file_size_bytes: int
    is_cached: bool = False


def validate_sec_url(url: str) -> None:
    """Validate that a URL points to an approved official SEC EDGAR domain.

    Args:
        url: URL string to inspect.

    Raises:
        InvalidSECUrlError: If the scheme is not https or the host is not an SEC domain.
    """
    if not url:
        raise InvalidSECUrlError("URL is empty.")
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise InvalidSECUrlError(f"Malformed URL '{url}': {exc}") from exc

    if parsed.scheme.lower() not in {"https", "http"}:
        raise InvalidSECUrlError(
            f"Insecure or invalid URL scheme '{parsed.scheme}': {url}"
        )

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_SEC_HOSTS:
        raise InvalidSECUrlError(
            f"Unauthorized host '{host}'. Filing downloads are restricted to approved SEC hosts: {ALLOWED_SEC_HOSTS}"
        )


class FilingDownloader:
    """Downloader for primary SEC EDGAR filing HTML documents."""

    def __init__(
        self,
        settings: Settings | None = None,
        storage_dir: Path | None = None,
        max_size_bytes: int | None = None,
        timeout: float = 20.0,
        requests_per_second: float = 8.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage_dir = storage_dir or (BASE_DIR / self.settings.FILINGS_STORAGE_DIR)
        self.max_size_bytes = max_size_bytes or self.settings.MAX_DOCUMENT_SIZE_BYTES
        self.timeout = timeout
        self.min_interval = 1.0 / requests_per_second
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.last_request_time: float = 0.0

        # Validate User-Agent configuration (allow placeholder or empty during initialization)
        if self.settings.SEC_USER_AGENT and self.settings.SEC_USER_AGENT.strip():
            validate_user_agent(self.settings.SEC_USER_AGENT, allow_placeholder=True)

        ua_val = (
            self.settings.SEC_USER_AGENT.strip() if self.settings.SEC_USER_AGENT else ""
        )
        self._headers = {
            "User-Agent": ua_val,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        }

    def _throttle(self) -> None:
        """Enforce rate limiting between outbound requests."""
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.monotonic()

    def get_filing_storage_path(
        self, cik: str, accession_number: str, primary_document: str
    ) -> Path:
        """Derive a safe, isolated local filesystem path for a filing.

        Args:
            cik: 10-digit CIK.
            accession_number: Accession number (e.g., 0000320193-23-000106).
            primary_document: Document filename (e.g., aapl-20230930.htm).

        Returns:
            Path: Destination file path under datasets/filings/{cik}/{accession_nodash}/.
        """
        norm_cik = normalize_cik(cik)
        accn_nodash = accession_number.replace("-", "").strip()
        safe_filename = Path(primary_document).name  # Defend against path traversal
        return self.storage_dir / norm_cik / accn_nodash / safe_filename

    def download_filing(
        self,
        cik: str,
        ticker: str,
        accession_number: str,
        form: str,
        primary_document: str,
        source_url: str,
        force_refresh: bool = False,
    ) -> DownloadedFiling:
        """Download and validate an official SEC filing document.

        Args:
            cik: Central Index Key.
            ticker: Stock ticker symbol.
            accession_number: Unique SEC accession number.
            form: Filing form (e.g., '10-K', '10-Q').
            primary_document: Primary document filename.
            source_url: Direct archive URL.
            force_refresh: If True, re-download even if already present locally.

        Returns:
            DownloadedFiling: Descriptor containing local file path and metadata.

        Raises:
            InvalidSECUrlError: If source_url is not on an approved SEC domain.
            FilingSizeExceededError: If the document exceeds max_size_bytes.
            SECAuthenticationError: On 403 Forbidden.
            SECNotFoundError: On 404 Not Found.
            SECRateLimitError: On 429 Too Many Requests.
            FilingDownloadError: On network or validation failures.
        """
        validate_sec_url(source_url)
        norm_cik = normalize_cik(cik)
        dest_path = self.get_filing_storage_path(
            norm_cik, accession_number, primary_document
        )

        # Check if already present on disk
        if dest_path.exists() and not force_refresh:
            content = dest_path.read_bytes()
            if len(content) > 0:
                doc_hash = hashlib.sha256(content).hexdigest()
                logger.info(
                    "Filing %s already cached locally at %s (%d bytes)",
                    accession_number,
                    dest_path,
                    len(content),
                )
                return DownloadedFiling(
                    accession_number=accession_number,
                    cik=norm_cik,
                    ticker=ticker.upper(),
                    form=form.upper(),
                    primary_document=primary_document,
                    source_url=source_url,
                    local_file_path=dest_path,
                    document_hash=doc_hash,
                    file_size_bytes=len(content),
                    is_cached=True,
                )

        logger.info(
            "Downloading filing %s for %s from %s", accession_number, ticker, source_url
        )

        # Enforce valid non-placeholder User-Agent on live download
        validate_user_agent(self.settings.SEC_USER_AGENT, allow_placeholder=False)

        attempt = 0
        while attempt <= self.max_retries:
            self._throttle()
            attempt += 1

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(source_url, headers=self._headers)

                if response.status_code == 200:
                    raw_bytes = response.content
                    size = len(raw_bytes)

                    if size == 0:
                        raise FilingDownloadError(
                            f"SEC returned empty document for {source_url}"
                        )

                    if size > self.max_size_bytes:
                        raise FilingSizeExceededError(
                            f"Filing size ({size} bytes) exceeds configured maximum limit of {self.max_size_bytes} bytes."
                        )

                    # Validate response is readable HTML or text
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        t in content_type
                        for t in ["html", "text", "xml", "octet-stream"]
                    ):
                        logger.warning(
                            "Unusual Content-Type for filing: %s", content_type
                        )

                    # Save to local disk atomically
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(raw_bytes)

                    doc_hash = hashlib.sha256(raw_bytes).hexdigest()
                    logger.info(
                        "Successfully downloaded %s (%d bytes) to %s",
                        accession_number,
                        size,
                        dest_path,
                    )

                    return DownloadedFiling(
                        accession_number=accession_number,
                        cik=norm_cik,
                        ticker=ticker.upper(),
                        form=form.upper(),
                        primary_document=primary_document,
                        source_url=source_url,
                        local_file_path=dest_path,
                        document_hash=doc_hash,
                        file_size_bytes=size,
                        is_cached=False,
                    )

                elif response.status_code == 404:
                    raise SECNotFoundError(
                        f"SEC filing document not found (404) at {source_url}"
                    )

                elif response.status_code == 403:
                    raise SECAuthenticationError(
                        f"SEC rejected request (403 Forbidden). Ensure SEC_USER_AGENT complies with guidelines: {source_url}"
                    )

                elif response.status_code == 429:
                    logger.warning(
                        "SEC Rate limit encountered (429) downloading %s, attempt %d",
                        source_url,
                        attempt,
                    )
                    if attempt > self.max_retries:
                        raise SECRateLimitError(
                            "SEC EDGAR rate limit (429) exceeded. Retry later."
                        )
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                    continue

                elif response.status_code >= 500:
                    logger.warning(
                        "SEC server error %d on attempt %d: %s",
                        response.status_code,
                        attempt,
                        source_url,
                    )
                    if attempt > self.max_retries:
                        raise SECNetworkError(
                            f"SEC server error HTTP {response.status_code} for {source_url}"
                        )
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                    continue

                else:
                    raise FilingDownloadError(
                        f"Unexpected HTTP {response.status_code} from SEC archive: {source_url}"
                    )

            except httpx.RequestError as exc:
                logger.warning(
                    "Network failure downloading %s, attempt %d: %s",
                    source_url,
                    attempt,
                    exc,
                )
                if attempt > self.max_retries:
                    raise SECNetworkError(
                        f"Failed to connect to SEC archive {source_url}: {exc}"
                    ) from exc
                time.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        raise FilingDownloadError(f"Max retries exceeded for filing URL: {source_url}")
