"""Data Normalizer and Canonical Financial Observation Schemas.

Defines the normalized data representation for all SEC XBRL financial facts
and provides normalization, deduplication, and validation logic.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PeriodType = Literal["annual", "quarterly", "ytd", "instant"]


class FinancialObservation(BaseModel):
    """Normalized financial observation from SEC EDGAR filings."""

    company_ticker: str = Field(..., description="Normalized company ticker symbol")
    company_cik: str = Field(..., description="10-digit zero-padded CIK")
    company_name: str = Field(..., description="Official registered company title")
    metric_name: str = Field(..., description="Canonical metric name (e.g., Revenue)")
    statement_type: str = Field(
        ...,
        description="Financial statement category (Income Statement, Balance Sheet, Cash Flow)",
    )
    original_tag: str = Field(
        ..., description="Raw SEC XBRL tag (e.g., us-gaap:Revenues)"
    )
    numeric_value: float = Field(
        ..., description="Raw numerical value reported by issuer"
    )
    unit: str = Field(..., description="Unit of measurement (e.g., USD, shares)")
    period_start: str | None = Field(
        None, description="Start date of period (YYYY-MM-DD)"
    )
    period_end: str = Field(
        ..., description="End date / point-in-time date (YYYY-MM-DD)"
    )
    duration_days: int | None = Field(
        None, description="Number of days spanned by period for flow statements"
    )
    period_type: PeriodType = Field(
        ...,
        description="Temporal classification: 'annual', 'quarterly', 'ytd', or 'instant'",
    )
    fiscal_year: int | None = Field(None, description="Fiscal year reported by issuer")
    fiscal_period: str | None = Field(
        None, description="Fiscal period (e.g., FY, Q1, Q2, Q3, Q4)"
    )
    filing_date: str = Field(
        ..., description="Date filing was accepted by SEC (YYYY-MM-DD)"
    )
    filing_type: str = Field(
        ..., description="Filing form code (e.g., 10-K, 10-Q, 10-K/A)"
    )
    accession_number: str = Field(..., description="SEC EDGAR unique accession number")
    source_url: str = Field(
        ..., description="Canonical SEC archive link to source document"
    )


def calculate_duration_days(start_str: str | None, end_str: str) -> int | None:
    """Calculate the duration in days between two ISO date strings."""
    if not start_str:
        return None
    try:
        d_start = datetime.strptime(start_str, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_str, "%Y-%m-%d").date()
        return (d_end - d_start).days
    except (ValueError, TypeError):
        return None


def classify_period_type(
    is_instant: bool,
    duration_days: int | None,
    form: str,
    fiscal_period: str | None,
) -> PeriodType:
    """Classify the period type accurately to prevent conflating YTD with standalone quarters.

    Args:
        is_instant: True for Balance Sheet point-in-time items.
        duration_days: Duration in days for flow items.
        form: SEC form type (e.g., '10-K', '10-Q').
        fiscal_period: SEC fiscal period code (e.g., 'FY', 'Q1', 'Q2', 'Q3').

    Returns:
        PeriodType: One of 'annual', 'quarterly', 'ytd', or 'instant'.
    """
    if is_instant:
        return "instant"

    if duration_days is None:
        if form.upper().startswith("10-K"):
            return "annual"
        return "quarterly"

    # Annual flow statements generally span 330 to 390 days
    if 330 <= duration_days <= 390 or (
        fiscal_period == "FY" and form.upper().startswith("10-K")
    ):
        return "annual"

    # Standalone quarterly flow statements span ~60 to 115 days (~3 months)
    if 60 <= duration_days <= 115:
        return "quarterly"

    # Year-to-date or cumulative durations (e.g. 6-month Q1+Q2 or 9-month Q1+Q2+Q3 in 10-Q)
    if 150 <= duration_days <= 310:
        return "ytd"

    # Default fallback based on form
    if form.upper().startswith("10-K"):
        return "annual"
    return "quarterly"


def deduplicate_observations(
    observations: list[FinancialObservation],
) -> list[FinancialObservation]:
    """Deduplicate observations favoring the most recently filed record for identical periods.

    Deduplication key:
        (company_cik, metric_name, period_end, filing_type, period_start or '')

    Args:
        observations: Raw list of observations.

    Returns:
        list[FinancialObservation]: Deduplicated observations.
    """
    latest_by_key: dict[tuple[str, str, str, str, str], FinancialObservation] = {}

    for obs in observations:
        key = (
            obs.company_cik,
            obs.metric_name,
            obs.period_end,
            obs.period_type,
            obs.period_start or "",
        )

        existing = latest_by_key.get(key)
        if existing is None:
            latest_by_key[key] = obs
        else:
            # If a later filing date is found, keep the newer amendment
            if obs.filing_date > existing.filing_date or (
                obs.filing_date == existing.filing_date
                and "10-K" in obs.filing_type
                and "10-K" not in existing.filing_type
            ):
                latest_by_key[key] = obs

    # Return sorted by metric_name, then period_end descending
    return sorted(
        latest_by_key.values(),
        key=lambda x: (x.metric_name, x.period_end, x.period_type),
        reverse=True,
    )
