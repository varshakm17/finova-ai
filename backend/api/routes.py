"""API route definitions for Finova AI.

Provides health diagnostics, company identity resolution, filing discovery,
and structured financial observation retrieval via SEC EDGAR.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.data.company_service import CompanyService, normalize_ticker
from backend.data.data_normalizer import FinancialObservation
from backend.data.financial_extractor import FinancialExtractor
from backend.data.sec_client import (
    SECClient,
    SECConfigurationError,
    SECNotFoundError,
    SECRateLimitError,
)
from backend.data.storage import Database
from backend.utils.logger import get_logger
from config.settings import get_settings

logger = get_logger("routes")
router = APIRouter()

# Service Singletons
_db = Database()
_company_service = CompanyService()
_financial_extractor = FinancialExtractor()


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Schema for application health check response."""

    status: str = Field(..., description="Application operational status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current deployment environment")


class CompanyIdentityResponse(BaseModel):
    """Schema for company identification details."""

    ticker: str = Field(..., description="Normalized stock ticker symbol")
    cik: str = Field(..., description="10-digit zero-padded CIK")
    name: str = Field(..., description="Official registered company title")


class CompanyMetadataResponse(BaseModel):
    """Schema for complete company metadata and profile."""

    ticker: str = Field(..., description="Company ticker symbol")
    cik: str = Field(..., description="10-digit CIK")
    name: str = Field(..., description="Official registered company title")
    sic: str | None = Field(None, description="Standard Industrial Classification code")
    sic_description: str | None = Field(None, description="SIC industry title")
    fiscal_year_end: str | None = Field(None, description="Fiscal year end date (MMDD)")
    state_location: str | None = Field(None, description="Headquarters state / country")


class FilingMetadataResponse(BaseModel):
    """Schema for SEC filing record."""

    accession_number: str = Field(..., description="Unique SEC accession number")
    cik: str = Field(..., description="10-digit CIK")
    form: str = Field(..., description="Filing form code (10-K, 10-Q, 8-K)")
    filing_date: str = Field(..., description="Date filing was accepted (YYYY-MM-DD)")
    report_date: str | None = Field(None, description="Period end date for report")
    acceptance_date: str | None = Field(None, description="Timestamp of SEC acceptance")
    primary_document: str | None = Field(None, description="Primary filing file name")
    primary_doc_description: str | None = Field(
        None, description="Document description"
    )
    is_xbrl: bool = Field(False, description="Whether filing includes XBRL data")
    is_inline_xbrl: bool = Field(
        False, description="Whether filing includes Inline XBRL"
    )
    url: str | None = Field(None, description="Direct SEC archive URL")


# -----------------------------------------------------------------------------
# Diagnostic / Health Endpoints (Session 01 preservation)
# -----------------------------------------------------------------------------
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Health Check",
    description="Returns the operational status, application name, environment, and version.",
    tags=["Diagnostics"],
)
def get_health() -> HealthResponse:
    """Retrieve current service health and metadata."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )


# -----------------------------------------------------------------------------
# Company & Filing Endpoints (Session 02)
# -----------------------------------------------------------------------------
@router.get(
    "/companies/search",
    response_model=CompanyIdentityResponse,
    summary="Search Company Identity",
    description="Resolves a stock ticker symbol to official SEC identification (CIK and company name).",
    tags=["Companies"],
)
def search_company(
    ticker: str | None = Query(None, description="Stock ticker symbol (e.g., AAPL)"),
    query: str | None = Query(None, description="Alternative ticker query parameter"),
) -> CompanyIdentityResponse:
    """Search for company identity by ticker symbol."""
    target_ticker = ticker or query
    if not target_ticker or not target_ticker.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A 'ticker' query parameter must be provided.",
        )

    try:
        record = _company_service.get_company_by_ticker(target_ticker)
    except SECConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error resolving ticker %s: %s", target_ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving company directory from SEC.",
        ) from exc

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{target_ticker}' not found in SEC EDGAR directory.",
        )

    return CompanyIdentityResponse(**record)


@router.get(
    "/companies/{ticker}",
    response_model=CompanyMetadataResponse,
    summary="Get Company Metadata",
    description="Retrieves company profile, business classification, and CIK details.",
    tags=["Companies"],
)
def get_company_metadata(ticker: str) -> CompanyMetadataResponse:
    """Retrieve full company metadata, querying SEC submissions if not cached."""
    norm_ticker = normalize_ticker(ticker)

    # 1. Check local database
    existing = _db.get_company_by_ticker(norm_ticker)
    if existing and existing.get("sic"):
        return CompanyMetadataResponse(
            ticker=existing["ticker"],
            cik=existing["cik"],
            name=existing["name"],
            sic=existing.get("sic"),
            sic_description=existing.get("sic_description"),
            fiscal_year_end=existing.get("fiscal_year_end"),
            state_location=existing.get("state_location"),
        )

    # 2. Resolve CIK via company service
    try:
        identity = _company_service.get_company_by_ticker(norm_ticker)
    except SECConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{norm_ticker}' not found.",
        )

    cik = identity["cik"]

    # 3. Fetch submissions from SEC to get rich business profile
    try:
        sec_client = SECClient()
        submissions = sec_client.get_company_submissions(cik)
    except SECConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except SECNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SECRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("Failed to fetch submissions for CIK %s: %s", cik, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve company submissions from SEC EDGAR.",
        ) from exc

    sic_code = submissions.get("sic")
    sic_desc = submissions.get("sicDescription")
    fiscal_end = submissions.get("fiscalYearEnd")
    state_loc = submissions.get("stateOfIncorporation") or submissions.get(
        "stateLocation"
    )

    company_payload = {
        "cik": cik,
        "ticker": norm_ticker,
        "name": submissions.get("name", identity["name"]),
        "sic": str(sic_code) if sic_code is not None else None,
        "sic_description": sic_desc,
        "fiscal_year_end": fiscal_end,
        "state_location": state_loc,
    }

    _db.save_company(company_payload)

    return CompanyMetadataResponse(**company_payload)


@router.get(
    "/companies/{ticker}/filings",
    response_model=list[FilingMetadataResponse],
    summary="Get Company Filings",
    description="Retrieves a list of SEC EDGAR filings for a company with optional form filtering.",
    tags=["Filings"],
)
def get_company_filings(
    ticker: str,
    form_type: str | None = Query(
        None, description="Filter by form type (e.g., 10-K, 10-Q)"
    ),
) -> list[FilingMetadataResponse]:
    """Retrieve filing metadata for a company."""
    norm_ticker = normalize_ticker(ticker)

    # Resolve company
    identity = _company_service.get_company_by_ticker(norm_ticker)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{norm_ticker}' not found.",
        )

    cik = identity["cik"]

    # Check database cache first
    existing_filings = _db.get_filings(cik=cik, form_type=form_type)
    if existing_filings:
        return [
            FilingMetadataResponse(
                accession_number=f["accession_number"],
                cik=f["cik"],
                form=f["form"],
                filing_date=f["filing_date"],
                report_date=f.get("report_date"),
                acceptance_date=f.get("acceptance_date"),
                primary_document=f.get("primary_document"),
                primary_doc_description=f.get("primary_doc_description"),
                is_xbrl=bool(f.get("is_xbrl")),
                is_inline_xbrl=bool(f.get("is_inline_xbrl")),
                url=f.get("url"),
            )
            for f in existing_filings
        ]

    # Otherwise fetch live from SEC
    try:
        sec_client = SECClient()
        filings = sec_client.get_company_filings(cik=cik, form_type=form_type)
        # Ensure company exists in DB to satisfy foreign keys
        _db.save_company({"cik": cik, "ticker": norm_ticker, "name": identity["name"]})
        _db.save_filings(cik, filings)
    except SECConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("Failed to fetch filings for %s: %s", cik, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve company filings from SEC EDGAR.",
        ) from exc

    return [
        FilingMetadataResponse(
            accession_number=f["accession_number"],
            cik=f["cik"],
            form=f["form"],
            filing_date=f["filing_date"],
            report_date=f.get("report_date"),
            acceptance_date=f.get("acceptance_date"),
            primary_document=f.get("primary_document"),
            primary_doc_description=f.get("primary_doc_description"),
            is_xbrl=bool(f.get("is_xbrl")),
            is_inline_xbrl=bool(f.get("is_inline_xbrl")),
            url=f.get("url"),
        )
        for f in filings
    ]


@router.get(
    "/companies/{ticker}/financials",
    response_model=list[FinancialObservation],
    summary="Get Financial Observations",
    description="Returns structured, normalized financial observations (Income Statement, Balance Sheet, Cash Flow).",
    tags=["Financials"],
)
def get_company_financials(
    ticker: str,
    start_year: int | None = Query(
        None, description="Filter observations starting from fiscal year"
    ),
    end_year: int | None = Query(
        None, description="Filter observations up to fiscal year"
    ),
    period_type: str | None = Query(
        None, description="Filter by 'annual', 'quarterly', or 'instant'"
    ),
) -> list[FinancialObservation]:
    """Retrieve structured financial metrics for a company across years."""
    norm_ticker = normalize_ticker(ticker)

    identity = _company_service.get_company_by_ticker(norm_ticker)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{norm_ticker}' not found.",
        )

    cik = identity["cik"]

    # Check if we already have observations in DB
    existing_obs = _db.get_financial_observations(
        ticker_or_cik=norm_ticker,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )
    if existing_obs:
        return existing_obs

    # Otherwise fetch company facts from SEC, extract and persist
    try:
        sec_client = SECClient()
        facts = sec_client.get_company_facts(cik)
        observations = _financial_extractor.extract_company_facts(
            company_facts=facts,
            ticker=norm_ticker,
            company_name=identity["name"],
        )

        _db.save_company({"cik": cik, "ticker": norm_ticker, "name": identity["name"]})
        _db.save_financial_observations(observations)
    except SECConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.error("Failed to extract financial facts for %s: %s", norm_ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve or parse company facts from SEC EDGAR.",
        ) from exc

    return _db.get_financial_observations(
        ticker_or_cik=norm_ticker,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )


@router.get(
    "/companies/{ticker}/financials/{metric}",
    response_model=list[FinancialObservation],
    summary="Get Specific Financial Metric History",
    description="Returns chronological observations for a designated financial metric (e.g., 'Revenue', 'Net Income').",
    tags=["Financials"],
)
def get_metric_history(
    ticker: str,
    metric: str,
    start_year: int | None = Query(None, description="Start fiscal year"),
    end_year: int | None = Query(None, description="End fiscal year"),
    period_type: str | None = Query(
        None, description="Period type ('annual', 'quarterly')"
    ),
) -> list[FinancialObservation]:
    """Retrieve historical observations for a specific named metric."""
    norm_ticker = normalize_ticker(ticker)

    # Make sure facts are populated
    observations = get_company_financials(
        ticker=norm_ticker,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )

    # Filter by metric name (case-insensitive)
    target_metric = metric.strip().lower()
    matched = [obs for obs in observations if obs.metric_name.lower() == target_metric]

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric '{metric}' not found for company '{norm_ticker}'.",
        )

    return matched
