"""SEC EDGAR API Client.

Provides compliant, rate-limited, and resilient access to official SEC EDGAR data endpoints
in accordance with SEC fair-access policies.
"""

import re
import time
from typing import Any

import httpx

from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("sec_client")

# SEC EDGAR Endpoints
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVES_BASE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{primary_doc}"
)


class SECError(Exception):
    """Base exception for SEC EDGAR integration errors."""


class SECConfigurationError(SECError):
    """Raised when SEC configuration (User-Agent) is missing or invalid."""


class SECAuthenticationError(SECError):
    """Raised when SEC rejects request with 403 Forbidden."""


class SECNotFoundError(SECError):
    """Raised when requested SEC resource or CIK is not found (404)."""


class SECRateLimitError(SECError):
    """Raised when SEC rate limit is reached (429)."""


class SECNetworkError(SECError):
    """Raised on network failure or unexpected HTTP error."""


def normalize_cik(cik: str | int) -> str:
    """Format a CIK as a standard 10-digit zero-padded string.

    Args:
        cik: Raw CIK as integer or string (e.g., 320193 or '0000320193').

    Returns:
        str: 10-digit zero-padded string (e.g., '0000320193').

    Raises:
        ValueError: If cik cannot be converted to a positive integer.
    """
    cleaned = str(cik).strip()
    if not cleaned.isdigit() and not (
        cleaned.startswith("CIK") and cleaned[3:].isdigit()
    ):
        raise ValueError(f"Invalid CIK format: {cik}")
    cleaned = cleaned.removeprefix("CIK")
    return f"{int(cleaned):010d}"


PLACEHOLDER_EMAILS = {
    "contact@example.com",
    "admincontact@domain.com",
    "user@example.com",
    "your-email@example.com",
    "email@domain.com",
    "sample@samplecompany.com",
}

PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "domain.com",
    "sample.com",
    "samplecompany.com",
    "yourdomain.com",
}


def is_placeholder_user_agent(user_agent: str | None) -> bool:
    """Check whether User-Agent header contains known example or placeholder contact identities."""
    if not user_agent or not user_agent.strip():
        return True
    ua_clean = user_agent.strip().lower()
    for placeholder in PLACEHOLDER_EMAILS:
        if placeholder in ua_clean:
            return True
    match = re.search(r"@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", ua_clean)
    if match:
        domain = match.group(1).rstrip(")>]")
        if domain in PLACEHOLDER_DOMAINS:
            return True
    return False


def mask_user_agent(user_agent: str | None) -> str:
    """Mask email/contact info in User-Agent header for safe public display."""
    if not user_agent or not user_agent.strip():
        return "[NOT CONFIGURED]"

    def _mask_email(match: re.Match) -> str:
        user, domain = match.group(1), match.group(2)
        masked_user = user[0] + "***" if user else "***"
        parts = domain.split(".")
        tld = parts[-1] if len(parts) > 1 else "com"
        return f"{masked_user}@{parts[0][0]}***.{tld}"

    return re.sub(
        r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        _mask_email,
        user_agent.strip(),
    )


def validate_user_agent(
    user_agent: str | None, allow_placeholder: bool = False
) -> None:
    """Validate that the configured User-Agent complies with SEC guidelines.

    The SEC requires: Sample Company Name AdminContact@<sample company domain>.com

    Args:
        user_agent: User-Agent string to inspect.
        allow_placeholder: If False, rejects known placeholder identities (e.g. contact@example.com).

    Raises:
        SECConfigurationError: If missing, placeholder, or invalid syntax.
    """
    if not user_agent or not user_agent.strip():
        raise SECConfigurationError(
            "SEC_USER_AGENT is not configured. SEC EDGAR fair-access policy requires a declared "
            "User-Agent in the format: 'ApplicationName AdminContact@domain.com'. "
            "Please configure SEC_USER_AGENT in your .env file."
        )

    ua_clean = user_agent.strip()
    # Check for email presence (user@domain.tld)
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    if not re.search(email_pattern, ua_clean):
        raise SECConfigurationError(
            f"SEC_USER_AGENT '{ua_clean}' does not contain a valid contact email. "
            "SEC EDGAR guidelines require a valid contact email in the User-Agent header "
            "(e.g., 'FinovaAI-Research/0.1.0 (admin@myfirm.org)')."
        )

    if not allow_placeholder and is_placeholder_user_agent(ua_clean):
        raise SECConfigurationError(
            f"SEC_USER_AGENT '{ua_clean}' contains an unconfigured placeholder identity. "
            "SEC EDGAR fair-access policy requires a valid, genuine institutional or researcher contact email. "
            "Please configure SEC_USER_AGENT in your .env file with your actual name/organization and email."
        )


class SECClient:
    """HTTP client for SEC EDGAR APIs with rate limiting and retry handling."""

    def __init__(
        self,
        settings: Settings | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        requests_per_second: float = 8.0,
        timeout: float = 12.0,
        allow_placeholder: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.min_interval = 1.0 / requests_per_second
        self.timeout = timeout
        self.last_request_time: float = 0.0
        self.allow_placeholder = allow_placeholder

        # Validate User-Agent upon instantiation
        validate_user_agent(
            self.settings.SEC_USER_AGENT, allow_placeholder=allow_placeholder
        )

        self._headers = {
            "User-Agent": self.settings.SEC_USER_AGENT.strip(),
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/plain, */*",
        }

    def _throttle(self) -> None:
        """Enforce rate limiting between outbound requests."""
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.monotonic()

    def _request(self, url: str) -> dict[str, Any]:
        """Perform an HTTP GET request with retry handling and fair-access throttling.

        Args:
            url: SEC endpoint URL.

        Returns:
            dict[str, Any]: Parsed JSON response.

        Raises:
            SECConfigurationError: If User-Agent is unconfigured or a placeholder.
            SECAuthenticationError: On 403 Forbidden.
            SECNotFoundError: On 404 Not Found.
            SECRateLimitError: On 429 Too Many Requests after retries.
            SECNetworkError: On persistent network or HTTP failures.
        """
        # Validate that live outbound SEC calls do not use a placeholder email
        validate_user_agent(self.settings.SEC_USER_AGENT, allow_placeholder=False)

        attempt = 0
        while attempt <= self.max_retries:
            self._throttle()
            attempt += 1

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=self._headers)

                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as err:
                        logger.error(
                            "Failed to parse JSON response from %s: %s", url, err
                        )
                        raise SECNetworkError(
                            f"Invalid JSON returned from SEC endpoint: {url}"
                        ) from err

                elif response.status_code == 404:
                    logger.warning("SEC resource not found (404): %s", url)
                    raise SECNotFoundError(f"SEC resource not found at URL: {url}")

                elif response.status_code == 403:
                    logger.error(
                        "SEC access forbidden (403). Check SEC_USER_AGENT: %s", url
                    )
                    raise SECAuthenticationError(
                        "SEC EDGAR returned 403 Forbidden. Ensure SEC_USER_AGENT follows SEC guidelines."
                    )

                elif response.status_code == 429:
                    logger.warning(
                        "SEC Rate limit encountered (429) on attempt %d of %d",
                        attempt,
                        self.max_retries,
                    )
                    if attempt > self.max_retries:
                        raise SECRateLimitError(
                            "SEC EDGAR rate limit (429) exceeded. Retry later."
                        )
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue

                elif response.status_code >= 500:
                    logger.warning(
                        "SEC server error (%d) on attempt %d: %s",
                        response.status_code,
                        attempt,
                        url,
                    )
                    if attempt > self.max_retries:
                        raise SECNetworkError(
                            f"SEC server error HTTP {response.status_code} for {url}"
                        )
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue

                else:
                    logger.error(
                        "Unexpected HTTP error %d from %s", response.status_code, url
                    )
                    raise SECNetworkError(
                        f"Unexpected HTTP {response.status_code} from SEC: {url}"
                    )

            except httpx.RequestError as exc:
                logger.warning("Network request error on attempt %d: %s", attempt, exc)
                if attempt > self.max_retries:
                    raise SECNetworkError(
                        f"Failed to connect to SEC endpoint {url}: {exc}"
                    ) from exc
                time.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        raise SECNetworkError(f"Max retries exceeded for SEC URL: {url}")

    def get_company_tickers(self) -> dict[str, Any]:
        """Fetch the master SEC company ticker mapping.

        Returns:
            dict[str, Any]: Dictionary mapping indexes to ticker/CIK/title records.
        """
        logger.info(
            "Fetching SEC company ticker directory from %s", SEC_COMPANY_TICKERS_URL
        )
        return self._request(SEC_COMPANY_TICKERS_URL)

    def get_company_submissions(self, cik: str | int) -> dict[str, Any]:
        """Fetch company submission history and profile metadata.

        Args:
            cik: Central Index Key (CIK).

        Returns:
            dict[str, Any]: Submission metadata, business profile, and recent filings.
        """
        formatted_cik = normalize_cik(cik)
        url = SEC_SUBMISSIONS_URL.format(cik=formatted_cik)
        logger.info("Fetching SEC submissions for CIK: %s", formatted_cik)
        return self._request(url)

    def get_company_facts(self, cik: str | int) -> dict[str, Any]:
        """Fetch company XBRL financial facts data.

        Args:
            cik: Central Index Key (CIK).

        Returns:
            dict[str, Any]: Company financial facts structure containing US-GAAP taxonomies.
        """
        formatted_cik = normalize_cik(cik)
        url = SEC_COMPANY_FACTS_URL.format(cik=formatted_cik)
        logger.info("Fetching SEC company facts for CIK: %s", formatted_cik)
        return self._request(url)

    def get_company_filings(
        self,
        cik: str | int,
        form_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and flatten recent filings list for a company.

        Args:
            cik: Central Index Key (CIK).
            form_type: Optional form filter (e.g., '10-K', '10-Q', '8-K').

        Returns:
            list[dict[str, Any]]: Normalized list of filing records.
        """
        submissions = self.get_company_submissions(cik)
        formatted_cik = normalize_cik(cik)
        cik_int = int(formatted_cik)

        filings_data = submissions.get("filings", {}).get("recent", {})
        if not filings_data or "accessionNumber" not in filings_data:
            return []

        accession_numbers = filings_data.get("accessionNumber", [])
        forms = filings_data.get("form", [])
        filing_dates = filings_data.get("filingDate", [])
        report_dates = filings_data.get("reportDate", [])
        acceptance_dates = filings_data.get("acceptanceDateTime", [])
        primary_docs = filings_data.get("primaryDocument", [])
        primary_descriptions = filings_data.get("primaryDocDescription", [])
        is_xbrls = filings_data.get("isXBRL", [])
        is_inline_xbrls = filings_data.get("isInlineXBRL", [])

        normalized_filings: list[dict[str, Any]] = []

        target_form = form_type.upper().strip() if form_type else None

        for idx, acc_num in enumerate(accession_numbers):
            form = forms[idx] if idx < len(forms) else ""
            if target_form and form.upper() != target_form:
                continue

            primary_doc = primary_docs[idx] if idx < len(primary_docs) else ""
            accession_nodash = acc_num.replace("-", "")

            # Construct direct SEC archive URL if primary doc exists
            archive_url = ""
            if primary_doc:
                archive_url = SEC_ARCHIVES_BASE_URL.format(
                    cik_int=cik_int,
                    accession_nodash=accession_nodash,
                    primary_doc=primary_doc,
                )

            record = {
                "accession_number": acc_num,
                "cik": formatted_cik,
                "form": form,
                "filing_date": filing_dates[idx] if idx < len(filing_dates) else "",
                "report_date": report_dates[idx] if idx < len(report_dates) else "",
                "acceptance_date": acceptance_dates[idx]
                if idx < len(acceptance_dates)
                else "",
                "primary_document": primary_doc,
                "primary_doc_description": (
                    primary_descriptions[idx] if idx < len(primary_descriptions) else ""
                ),
                "is_xbrl": bool(is_xbrls[idx]) if idx < len(is_xbrls) else False,
                "is_inline_xbrl": (
                    bool(is_inline_xbrls[idx]) if idx < len(is_inline_xbrls) else False
                ),
                "url": archive_url,
            }
            normalized_filings.append(record)

        return normalized_filings
