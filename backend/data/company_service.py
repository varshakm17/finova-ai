"""Company Identification and Ticker Mapping Service.

Provides ticker-to-CIK resolution, company search, and local caching
in compliance with SEC data structures.
"""

import json
import time
from pathlib import Path
from typing import Any

from backend.data.sec_client import SECClient, normalize_cik
from backend.utils.logger import get_logger
from config.settings import BASE_DIR, get_settings

logger = get_logger("company_service")

CACHE_DIR = BASE_DIR / "datasets" / "cache"
CACHE_FILE = CACHE_DIR / "company_tickers.json"
CACHE_TTL_SECONDS = 86400  # 24 hours


def normalize_ticker(ticker: str) -> str:
    """Normalize a stock ticker symbol for consistent lookup.

    Replaces dots with hyphens (e.g., BRK.B -> BRK-B), removes whitespace,
    and converts to uppercase.

    Args:
        ticker: Raw ticker symbol.

    Returns:
        str: Normalized uppercase ticker symbol.
    """
    if not ticker:
        return ""
    cleaned = ticker.strip().upper()
    return cleaned.replace(".", "-")


class CompanyService:
    """Service for resolving company tickers, CIKs, and corporate identity."""

    def __init__(
        self,
        sec_client: SECClient | None = None,
        cache_path: Path | None = None,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self.sec_client = sec_client
        self.cache_path = cache_path or CACHE_FILE
        self.cache_ttl = cache_ttl
        self._by_ticker: dict[str, dict[str, Any]] = {}
        self._by_cik: dict[str, dict[str, Any]] = {}
        self._loaded: bool = False

    def _get_client(self) -> SECClient:
        """Lazily initialize SECClient if not provided."""
        if self.sec_client is None:
            self.sec_client = SECClient(settings=get_settings())
        return self.sec_client

    def _load_from_cache(self) -> dict[str, Any] | None:
        """Attempt to read ticker mapping from local cache if still valid."""
        if not self.cache_path.exists():
            return None

        try:
            mtime = self.cache_path.stat().st_mtime
            age = time.time() - mtime
            if age > self.cache_ttl:
                logger.info(
                    "Ticker cache expired (age: %d seconds, TTL: %d)",
                    int(age),
                    self.cache_ttl,
                )
                return None

            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(
                "Loaded SEC company tickers from local cache: %s", self.cache_path
            )
            return data
        except (json.JSONDecodeError, OSError) as err:
            logger.warning(
                "Failed to load ticker cache from %s: %s", self.cache_path, err
            )
            return None

    def _save_to_cache(self, data: dict[str, Any]) -> None:
        """Write raw SEC ticker data to disk cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.info("Saved SEC company tickers to cache: %s", self.cache_path)
        except OSError as err:
            logger.warning(
                "Could not write ticker cache to %s: %s", self.cache_path, err
            )

    def load_tickers(self, force_refresh: bool = False) -> None:
        """Load company tickers from local cache or remote SEC endpoint.

        Args:
            force_refresh: If True, bypass cache and fetch fresh directory from SEC.
        """
        raw_data: dict[str, Any] | None = None

        if not force_refresh:
            raw_data = self._load_from_cache()

        if raw_data is None:
            client = self._get_client()
            raw_data = client.get_company_tickers()
            self._save_to_cache(raw_data)

        self._by_ticker.clear()
        self._by_cik.clear()

        # Parse SEC ticker format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        for entry in raw_data.values():
            if not isinstance(entry, dict):
                continue
            ticker_raw = entry.get("ticker")
            cik_raw = entry.get("cik_str")
            title_raw = entry.get("title", "")

            if not ticker_raw or cik_raw is None:
                continue

            norm_ticker = normalize_ticker(ticker_raw)
            norm_cik = normalize_cik(cik_raw)

            record = {
                "ticker": norm_ticker,
                "cik": norm_cik,
                "name": title_raw.strip(),
            }

            self._by_ticker[norm_ticker] = record
            self._by_cik[norm_cik] = record

        self._loaded = True
        logger.info("Indexed %d company tickers into memory", len(self._by_ticker))

    def _ensure_loaded(self) -> None:
        """Guarantee tickers are loaded prior to lookups."""
        if not self._loaded:
            self.load_tickers()

    def get_company_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        """Resolve a ticker symbol to company metadata and 10-digit CIK.

        Args:
            ticker: Ticker symbol (e.g., 'AAPL', 'msft', 'BRK.B').

        Returns:
            dict[str, Any] | None: Company record or None if not found.
        """
        self._ensure_loaded()
        norm_ticker = normalize_ticker(ticker)
        return self._by_ticker.get(norm_ticker)

    def get_company_by_cik(self, cik: str | int) -> dict[str, Any] | None:
        """Resolve a CIK to company metadata and ticker symbol.

        Args:
            cik: CIK as integer or string.

        Returns:
            dict[str, Any] | None: Company record or None if not found.
        """
        self._ensure_loaded()
        try:
            norm_cik = normalize_cik(cik)
        except ValueError:
            return None
        return self._by_cik.get(norm_cik)

    def search_companies(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search companies by ticker prefix or name substring.

        Args:
            query: Search query (ticker or corporate title).
            limit: Maximum results to return.

        Returns:
            list[dict[str, Any]]: Matching company records.
        """
        self._ensure_loaded()
        q_clean = query.strip().upper()
        if not q_clean:
            return []

        exact_matches: list[dict[str, Any]] = []
        prefix_matches: list[dict[str, Any]] = []
        name_matches: list[dict[str, Any]] = []

        for ticker, record in self._by_ticker.items():
            if ticker == q_clean:
                exact_matches.append(record)
            elif ticker.startswith(q_clean):
                prefix_matches.append(record)
            elif q_clean in record["name"].upper():
                name_matches.append(record)

            if (
                len(exact_matches) + len(prefix_matches) + len(name_matches)
                >= limit * 2
            ):
                break

        combined = exact_matches + prefix_matches + name_matches
        # Deduplicate while preserving rank
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for r in combined:
            if r["cik"] not in seen:
                seen.add(r["cik"])
                deduped.append(r)
            if len(deduped) >= limit:
                break

        return deduped
