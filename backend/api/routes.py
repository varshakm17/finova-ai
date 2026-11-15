"""API route definitions for Finova AI.

Provides health diagnostics, company identity resolution, filing discovery,
financial observations, and SEC filing document ingestion & chunking.
"""

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.data.company_service import CompanyService, normalize_ticker
from backend.data.data_normalizer import FinancialObservation
from backend.data.document_storage import DocumentStorage
from backend.data.filing_ingestion_service import FilingIngestionService
from backend.data.financial_extractor import FinancialExtractor
from backend.data.sec_client import (
    SECClient,
    SECConfigurationError,
    SECNotFoundError,
    SECRateLimitError,
)
from backend.data.storage import Database
from backend.evaluation.evidence_report import EvidenceReportGenerator
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.evaluation.retrieval_comparison import RetrievalComparator
from backend.evaluation.retrieval_evaluator import RetrievalEvaluator
from backend.finance.calculation_models import (
    CalculationReceipt,
    CalculationSummaryResponse,
    TriggerCalculationRequest,
)
from backend.finance.calculation_service import (
    ALL_CALCULATION_METRICS,
    CalculationService,
)
from backend.llm import get_llm_provider
from backend.rag.rag_models import (
    RAGAnswer,
    RAGCapabilitiesResponse,
    RAGRequest,
)
from backend.rag.rag_service import RAGService
from backend.retrieval.bm25_indexing_service import BM25IndexingService
from backend.retrieval.bm25_search import BM25SearchService
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.indexing_service import IndexingService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import (
    BM25IndexingRequest,
    BM25IndexingSummary,
    BM25IndexStatsResponse,
    BM25IndexStatusResponse,
    BM25SearchRequest,
    BM25SearchResult,
    EmbeddingStatusResponse,
    EvidenceValidationRequest,
    EvidenceValidationResult,
    HybridSearchRequest,
    HybridSearchResponse,
    IndexingRequest,
    IndexingSummary,
    IndexStatsResponse,
    RerankerStatusResponse,
    RetrievalComparisonRequest,
    RetrievalComparisonResponse,
    RetrievalEvaluationReport,
    RetrievalEvaluationRequest,
    SemanticSearchRequest,
    SemanticSearchResult,
)
from backend.retrieval.semantic_search import SemanticSearchService
from backend.utils.logger import get_logger
from backend.verification import VerificationRun, VerificationService
from config.settings import get_settings

logger = get_logger("routes")
router = APIRouter()

# Service Singletons
_db = Database()
_company_service = CompanyService()
_financial_extractor = FinancialExtractor()
_doc_storage = DocumentStorage(db=_db)
_ingestion_service = FilingIngestionService(
    db=_db,
    document_storage=_doc_storage,
    company_service=_company_service,
)
_calculation_service = CalculationService(
    db=_db,
    company_service=_company_service,
)
_settings = get_settings()
_indexing_service = IndexingService(
    document_storage=_doc_storage,
    settings=_settings,
)
_semantic_search_service = SemanticSearchService(
    document_storage=_doc_storage,
    settings=_settings,
)
_bm25_search_service = BM25SearchService(
    document_storage=_doc_storage,
    settings=_settings,
)
_bm25_indexing_service = BM25IndexingService(
    document_storage=_doc_storage,
    settings=_settings,
)
_hybrid_search_service = HybridSearchService(
    semantic_search_service=_semantic_search_service,
    bm25_search_service=_bm25_search_service,
    document_storage=_doc_storage,
    settings=_settings,
)
_reranker = CrossEncoderReranker(settings=_settings)
_evaluator = RetrievalEvaluator(settings=_settings)
_comparator = RetrievalComparator(
    hybrid_search_service=_hybrid_search_service,
    semantic_search_service=_semantic_search_service,
    bm25_search_service=_bm25_search_service,
    reranker=_reranker,
    document_storage=_doc_storage,
    settings=_settings,
)
_evidence_validator = EvidenceQualityValidator(
    document_storage=_doc_storage,
    settings=_settings,
)
_evidence_report_generator = EvidenceReportGenerator(
    hybrid_search_service=_hybrid_search_service,
    reranker=_reranker,
    validator=_evidence_validator,
    document_storage=_doc_storage,
    settings=_settings,
)
_evaluation_reports: dict[str, RetrievalEvaluationReport] = {}
_llm_provider = get_llm_provider(settings=_settings)
_verification_service = VerificationService(database=_db, settings=_settings)
_rag_service = RAGService(
    llm_provider=_llm_provider,
    verification_service=_verification_service,
    database=_db,
    settings=_settings,
)


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


class IngestFilingResponse(BaseModel):
    """Schema for filing document ingestion result."""

    document_id: str
    ticker: str
    cik: str
    company_name: str
    accession_number: str
    filing_type: str
    filing_date: str
    report_date: str | None = None
    processing_status: str
    sections_extracted: list[str] = Field(default_factory=list)
    sections_not_found: list[str] = Field(default_factory=list)
    total_chunks: int = 0
    document_hash: str = ""
    file_size_bytes: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class DocumentSummaryResponse(BaseModel):
    """Schema for ingested filing document summary."""

    document_id: str
    cik: str
    ticker: str
    company_name: str
    accession_number: str
    filing_type: str
    filing_date: str
    report_date: str | None = None
    primary_document: str
    source_url: str
    processing_status: str
    document_hash: str
    created_at: str
    updated_at: str


class DocumentDetailResponse(DocumentSummaryResponse):
    """Schema for complete document metadata with sections and chunk metrics."""

    sections: list[dict[str, Any]] = Field(default_factory=list)
    total_chunks: int = 0


class DocumentChunkResponse(BaseModel):
    """Schema for an individual section-aware text chunk."""

    chunk_id: str
    document_id: str
    section_id: str
    ticker: str
    accession_number: str
    filing_type: str
    section_identifier: str
    section_title: str
    chunk_index: int
    chunk_text: str
    start_offset: int
    end_offset: int
    char_count: int
    source_url: str
    created_at: str


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
# Company & Filing Metadata Endpoints (Session 02)
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

    identity = _company_service.get_company_by_ticker(norm_ticker)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{norm_ticker}' not found.",
        )

    cik = identity["cik"]

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

    try:
        sec_client = SECClient()
        filings = sec_client.get_company_filings(cik=cik, form_type=form_type)
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

    existing_obs = _db.get_financial_observations(
        ticker_or_cik=norm_ticker,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )
    if existing_obs:
        return existing_obs

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

    observations = get_company_financials(
        ticker=norm_ticker,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )

    target_metric = metric.strip().lower()
    matched = [obs for obs in observations if obs.metric_name.lower() == target_metric]

    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric '{metric}' not found for company '{norm_ticker}'.",
        )

    return matched


# -----------------------------------------------------------------------------
# Filing Document Ingestion & Chunking Endpoints (Session 03)
# -----------------------------------------------------------------------------
@router.post(
    "/companies/{ticker}/filings/{accession_number}/ingest",
    response_model=IngestFilingResponse,
    summary="Ingest SEC Filing Document",
    description="Downloads the primary HTML filing, extracts disclosure sections, and creates text chunks.",
    tags=["Document Ingestion"],
)
def ingest_filing(
    ticker: str,
    accession_number: str,
    force_refresh: bool = Query(
        False, description="Re-download and re-chunk even if already ingested"
    ),
) -> IngestFilingResponse:
    """Trigger ingestion and section-aware chunking of a selected statutory filing."""
    clean_ticker = normalize_ticker(ticker)
    clean_accn = accession_number.strip()

    result = _ingestion_service.ingest_filing(
        ticker=clean_ticker,
        accession_number=clean_accn,
        force_refresh=force_refresh,
    )

    if result.processing_status == "failed":
        if "not found" in (result.error or "").lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=result.error
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Filing ingestion failed.",
        )

    return IngestFilingResponse(
        document_id=result.document_id,
        ticker=result.ticker,
        cik=result.cik,
        company_name=result.company_name,
        accession_number=result.accession_number,
        filing_type=result.filing_type,
        filing_date=result.filing_date,
        report_date=result.report_date,
        processing_status=result.processing_status,
        sections_extracted=result.sections_extracted,
        sections_not_found=result.sections_not_found,
        total_chunks=result.total_chunks,
        document_hash=result.document_hash,
        file_size_bytes=result.file_size_bytes,
        warnings=result.warnings,
        error=result.error,
    )


@router.get(
    "/companies/{ticker}/documents",
    response_model=list[DocumentSummaryResponse],
    summary="List Ingested Documents",
    description="Returns all previously ingested statutory documents for a company.",
    tags=["Document Ingestion"],
)
def list_ingested_documents(
    ticker: str,
    filing_type: str | None = Query(
        None, description="Filter by filing type (e.g., 10-K, 10-Q)"
    ),
) -> list[DocumentSummaryResponse]:
    """List ingested documents for a company."""
    clean_ticker = normalize_ticker(ticker)
    identity = _company_service.get_company_by_ticker(clean_ticker)
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    docs = _doc_storage.list_documents_for_company(
        ticker_or_cik=clean_ticker, filing_type=filing_type
    )
    return [
        DocumentSummaryResponse(
            document_id=d["document_id"],
            cik=d["cik"],
            ticker=d["ticker"],
            company_name=d["company_name"],
            accession_number=d["accession_number"],
            filing_type=d["filing_type"],
            filing_date=d["filing_date"],
            report_date=d.get("report_date"),
            primary_document=d["primary_document"],
            source_url=d["source_url"],
            processing_status=d["processing_status"],
            document_hash=d["document_hash"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
        for d in docs
    ]


@router.get(
    "/companies/{ticker}/documents/{accession_number}",
    response_model=DocumentDetailResponse,
    summary="Get Ingested Document Details",
    description="Returns detailed processing status, sections, and chunk count for an ingested document.",
    tags=["Document Ingestion"],
)
def get_document_details(
    ticker: str,
    accession_number: str,
) -> DocumentDetailResponse:
    """Retrieve details, sections, and chunk metrics for an ingested document."""
    clean_accn = accession_number.strip()
    doc = _doc_storage.get_document_by_accession(clean_accn)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with accession number '{clean_accn}' not found.",
        )

    sections = _doc_storage.get_sections_for_document(doc["document_id"])
    chunks = _doc_storage.get_chunks_for_document(doc["document_id"])

    return DocumentDetailResponse(
        document_id=doc["document_id"],
        cik=doc["cik"],
        ticker=doc["ticker"],
        company_name=doc["company_name"],
        accession_number=doc["accession_number"],
        filing_type=doc["filing_type"],
        filing_date=doc["filing_date"],
        report_date=doc.get("report_date"),
        primary_document=doc["primary_document"],
        source_url=doc["source_url"],
        processing_status=doc["processing_status"],
        document_hash=doc["document_hash"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        sections=sections,
        total_chunks=len(chunks),
    )


@router.get(
    "/companies/{ticker}/documents/{accession_number}/chunks",
    response_model=list[DocumentChunkResponse],
    summary="Retrieve Document Chunks",
    description="Returns stored section-aware chunks with full provenance and optional section filtering.",
    tags=["Document Ingestion"],
)
def get_document_chunks(
    ticker: str,
    accession_number: str,
    section_identifier: str | None = Query(
        None, description="Filter chunks by section identifier (e.g., ITEM_1A, ITEM_7)"
    ),
) -> list[DocumentChunkResponse]:
    """Retrieve chunks for an ingested document."""
    clean_accn = accession_number.strip()
    doc = _doc_storage.get_document_by_accession(clean_accn)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with accession number '{clean_accn}' not found.",
        )

    chunks = _doc_storage.get_chunks_for_document(
        document_id=doc["document_id"],
        section_identifier=section_identifier,
    )

    return [
        DocumentChunkResponse(
            chunk_id=c["chunk_id"],
            document_id=c["document_id"],
            section_id=c["section_id"],
            ticker=c["ticker"],
            accession_number=c["accession_number"],
            filing_type=c["filing_type"],
            section_identifier=c["section_identifier"],
            section_title=c["section_title"],
            chunk_index=c["chunk_index"],
            chunk_text=c["chunk_text"],
            start_offset=c["start_offset"],
            end_offset=c["end_offset"],
            char_count=c["char_count"],
            source_url=c["source_url"],
            created_at=c["created_at"],
        )
        for c in chunks
    ]


# -----------------------------------------------------------------------------
# Financial Calculation & Analysis Endpoints (Session 04)
# -----------------------------------------------------------------------------
@router.post(
    "/companies/{ticker}/calculations",
    response_model=CalculationSummaryResponse,
    summary="Calculate Company Financial Metrics",
    description="Executes deterministic Python calculations across financial observations for specified periods.",
    tags=["Financial Calculations"],
)
def calculate_company_financial_metrics(
    ticker: str,
    payload: TriggerCalculationRequest | None = None,
    start_year: int | None = Query(
        None, description="Earliest fiscal year to compute (inclusive)"
    ),
    end_year: int | None = Query(
        None, description="Latest fiscal year to compute (inclusive)"
    ),
    period_type: str | None = Query(
        None, description="Period type filter: 'annual' or 'quarterly'"
    ),
    metric: list[str] | None = Query(  # noqa: B008
        None, description="Optional metric names to filter calculation"
    ),
) -> CalculationSummaryResponse:
    """Trigger deterministic financial calculations for a company."""
    clean_ticker = normalize_ticker(ticker)

    # Reconcile query parameters and body payload
    effective_start = (
        payload.start_year if payload and payload.start_year is not None else start_year
    )
    effective_end = (
        payload.end_year if payload and payload.end_year is not None else end_year
    )
    effective_period = (
        payload.period_type
        if payload and payload.period_type
        else period_type or "annual"
    )
    effective_metrics = payload.metrics if payload and payload.metrics else metric

    if effective_period not in {"annual", "quarterly"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period_type '{effective_period}'. Must be 'annual' or 'quarterly'.",
        )

    if effective_metrics:
        invalid_metrics = [
            m
            for m in effective_metrics
            if m.lower().strip() not in ALL_CALCULATION_METRICS
        ]
        if invalid_metrics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported metric(s): {', '.join(invalid_metrics)}. Supported: {', '.join(ALL_CALCULATION_METRICS)}",
            )

    try:
        summary = _calculation_service.calculate_company_metrics(
            ticker=clean_ticker,
            start_year=effective_start,
            end_year=effective_end,
            period_type=effective_period,
            metrics=effective_metrics,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing calculations for %s: %s", clean_ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute financial calculations: {exc}",
        ) from exc

    return summary


@router.get(
    "/companies/{ticker}/calculations",
    response_model=list[CalculationReceipt],
    summary="List Calculated Financial Metrics",
    description="Retrieves stored calculation receipts for a company with optional metric and year filters.",
    tags=["Financial Calculations"],
)
def get_company_calculations(
    ticker: str,
    metric_name: str | None = Query(
        None, description="Filter by metric key (e.g. gross_profit_margin)"
    ),
    start_year: int | None = Query(None, description="Filter by earliest fiscal year"),
    end_year: int | None = Query(None, description="Filter by latest fiscal year"),
    period_type: str | None = Query(
        None, description="Filter by period type ('annual' or 'quarterly')"
    ),
) -> list[CalculationReceipt]:
    """Retrieve stored calculation receipts for a company."""
    clean_ticker = normalize_ticker(ticker)
    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    records = _db.get_financial_calculations(
        ticker_or_cik=clean_ticker,
        metric_name=metric_name,
        start_year=start_year,
        end_year=end_year,
        period_type=period_type,
    )
    return [CalculationReceipt(**r) for r in records]


@router.get(
    "/companies/{ticker}/calculations/{metric_name}",
    response_model=list[CalculationReceipt],
    summary="Get Specific Metric History",
    description="Retrieves chronological calculation receipts for a specific financial indicator.",
    tags=["Financial Calculations"],
)
def get_specific_metric_history(
    ticker: str,
    metric_name: str,
    period_type: str | None = Query(
        None, description="Filter by period type ('annual' or 'quarterly')"
    ),
) -> list[CalculationReceipt]:
    """Retrieve chronological history for a specific calculated metric."""
    clean_ticker = normalize_ticker(ticker)
    clean_metric = metric_name.lower().strip()

    if clean_metric not in ALL_CALCULATION_METRICS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Metric '{metric_name}' is not recognized. Supported: {', '.join(ALL_CALCULATION_METRICS)}",
        )

    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    records = _db.get_financial_calculations(
        ticker_or_cik=clean_ticker,
        metric_name=clean_metric,
        period_type=period_type,
    )
    return [CalculationReceipt(**r) for r in records]


@router.get(
    "/calculations/{calculation_id}",
    response_model=CalculationReceipt,
    summary="Get Calculation Receipt",
    description="Retrieves a single verifiable calculation receipt with complete formula and input provenance.",
    tags=["Financial Calculations"],
)
def get_calculation_receipt_by_id(calculation_id: str) -> CalculationReceipt:
    """Retrieve a single calculation receipt by its unique ID."""
    clean_id = calculation_id.strip()
    record = _db.get_financial_calculation_by_id(clean_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calculation receipt with ID '{clean_id}' not found.",
        )
    return CalculationReceipt(**record)


# -----------------------------------------------------------------------------
# Semantic Embeddings & Vector Indexing Endpoints (Session 05)
# -----------------------------------------------------------------------------
@router.post(
    "/companies/{ticker}/embeddings/index",
    response_model=IndexingSummary,
    summary="Index Company Document Chunks",
    description="Generates semantic embeddings for document chunks of a company and updates the vector index.",
    tags=["Semantic Search & Embeddings"],
)
def index_company_embeddings(
    ticker: str,
    payload: IndexingRequest | None = None,
    filing_type: str | None = Query(
        None, description="Optional filter by filing type (e.g. '10-K', '10-Q')"
    ),
    accession_number: str | None = Query(
        None, description="Optional filter by accession number"
    ),
    force_reindex: bool = Query(
        False, description="If True, re-indexes even if content hash matches"
    ),
) -> IndexingSummary:
    """Index document chunks for a company into the vector store."""
    clean_ticker = normalize_ticker(ticker)
    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    effective_filing_type = (
        payload.filing_type if payload and payload.filing_type else filing_type
    )
    effective_accn = (
        payload.accession_number
        if payload and payload.accession_number
        else accession_number
    )
    effective_force = payload.force_reindex if payload else force_reindex

    try:
        summary = _indexing_service.index_company_chunks(
            ticker=clean_ticker,
            filing_type=effective_filing_type,
            accession_number=effective_accn,
            force_reindex=effective_force,
        )
        return summary
    except Exception as exc:
        logger.error("Error indexing embeddings for %s: %s", clean_ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings: {exc}",
        ) from exc


@router.get(
    "/companies/{ticker}/embeddings/status",
    response_model=EmbeddingStatusResponse,
    summary="Get Company Embedding Status",
    description="Returns total available chunks, indexed chunks, pending, and failed status for a company.",
    tags=["Semantic Search & Embeddings"],
)
def get_company_embedding_status(ticker: str) -> EmbeddingStatusResponse:
    """Retrieve chunk embedding coverage diagnostics for a company."""
    clean_ticker = normalize_ticker(ticker)
    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    return _indexing_service.get_indexing_status(clean_ticker)


@router.post(
    "/search/semantic",
    response_model=list[SemanticSearchResult],
    summary="Semantic Similarity Search",
    description="Executes dense semantic similarity search over indexed SEC filing document chunks.",
    tags=["Semantic Search & Embeddings"],
)
def semantic_search(request: SemanticSearchRequest) -> list[SemanticSearchResult]:
    """Search filing chunks using dense vector embeddings."""
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or whitespace-only.",
        )

    clean_ticker = normalize_ticker(request.ticker) if request.ticker else None
    if clean_ticker:
        company = _company_service.get_company_by_ticker(clean_ticker)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ticker '{clean_ticker}' not found.",
            )

    try:
        results = _semantic_search_service.search(
            query=request.query,
            ticker=clean_ticker,
            filing_type=request.filing_type,
            section_identifier=request.section_identifier,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )
        return results
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing semantic search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic search failed: {exc}",
        ) from exc


@router.get(
    "/index/stats",
    response_model=IndexStatsResponse,
    summary="Get Vector Index Statistics",
    description="Returns operational statistics, active backend, and vector index size.",
    tags=["Semantic Search & Embeddings"],
)
def get_vector_index_stats() -> IndexStatsResponse:
    """Retrieve vector store index statistics."""
    return _indexing_service.get_index_stats()


# -----------------------------------------------------------------------------
# BM25 Sparse & Hybrid Search Endpoints (Session 06)
# -----------------------------------------------------------------------------
@router.post(
    "/companies/{ticker}/bm25/index",
    response_model=BM25IndexingSummary,
    summary="Index Company Chunks with BM25",
    description="Tokenizes document chunks for a company and updates the BM25 sparse index.",
    tags=["BM25 Sparse & Hybrid Search"],
)
def index_company_bm25(
    ticker: str,
    payload: BM25IndexingRequest | None = None,
    filing_type: str | None = Query(
        None, description="Optional filter by filing type (e.g. '10-K', '10-Q')"
    ),
    accession_number: str | None = Query(
        None, description="Optional filter by accession number"
    ),
    force_reindex: bool = Query(
        False, description="If True, re-indexes even if content hash matches"
    ),
) -> BM25IndexingSummary:
    """Index document chunks for a company into the BM25 sparse index."""
    clean_ticker = normalize_ticker(ticker)
    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    effective_filing_type = (
        payload.filing_type if payload and payload.filing_type else filing_type
    )
    effective_accn = (
        payload.accession_number
        if payload and payload.accession_number
        else accession_number
    )
    effective_force = payload.force_reindex if payload else force_reindex

    try:
        summary = _bm25_indexing_service.index_company_chunks(
            ticker=clean_ticker,
            filing_type=effective_filing_type,
            accession_number=effective_accn,
            force_reindex=effective_force,
        )
        return summary
    except Exception as exc:
        logger.error("Error indexing BM25 for %s: %s", clean_ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate BM25 index: {exc}",
        ) from exc


@router.get(
    "/companies/{ticker}/bm25/status",
    response_model=BM25IndexStatusResponse,
    summary="Get Company BM25 Index Status",
    description="Returns available chunks, indexed chunks, token counts, and average document length.",
    tags=["BM25 Sparse & Hybrid Search"],
)
def get_company_bm25_status(ticker: str) -> BM25IndexStatusResponse:
    """Retrieve BM25 indexing coverage diagnostics for a company."""
    clean_ticker = normalize_ticker(ticker)
    company = _company_service.get_company_by_ticker(clean_ticker)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ticker '{clean_ticker}' not found.",
        )

    return _bm25_indexing_service.get_indexing_status(clean_ticker)


@router.post(
    "/search/sparse",
    response_model=list[BM25SearchResult],
    summary="BM25 Lexical Keyword Search",
    description="Executes BM25Okapi sparse lexical search over indexed SEC filing document chunks.",
    tags=["BM25 Sparse & Hybrid Search"],
)
def sparse_search(request: BM25SearchRequest) -> list[BM25SearchResult]:
    """Search filing chunks using BM25 lexical keyword matching."""
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or whitespace-only.",
        )

    clean_ticker = normalize_ticker(request.ticker) if request.ticker else None
    if clean_ticker:
        company = _company_service.get_company_by_ticker(clean_ticker)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ticker '{clean_ticker}' not found.",
            )

    try:
        results = _bm25_search_service.search(
            query=request.query,
            ticker=clean_ticker,
            filing_type=request.filing_type,
            section_identifier=request.section_identifier,
            top_k=request.top_k,
        )
        return results
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing BM25 sparse search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"BM25 sparse search failed: {exc}",
        ) from exc


@router.post(
    "/search/hybrid",
    response_model=HybridSearchResponse,
    summary="Hybrid Search with Reciprocal Rank Fusion",
    description="Executes dense semantic and BM25 sparse retrieval and fuses results via RRF.",
    tags=["BM25 Sparse & Hybrid Search"],
)
def hybrid_search(request: HybridSearchRequest) -> HybridSearchResponse:
    """Execute multi-modal hybrid retrieval with Reciprocal Rank Fusion."""
    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or whitespace-only.",
        )

    clean_ticker = normalize_ticker(request.ticker) if request.ticker else None
    if clean_ticker:
        company = _company_service.get_company_by_ticker(clean_ticker)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Company with ticker '{clean_ticker}' not found.",
            )

    try:
        response = _hybrid_search_service.search(
            query=request.query,
            ticker=clean_ticker,
            filing_type=request.filing_type,
            section_identifier=request.section_identifier,
            top_k=request.top_k,
            rrf_constant=request.rrf_constant,
            dense_limit=request.dense_limit,
            sparse_limit=request.sparse_limit,
        )
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error executing hybrid search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hybrid search failed: {exc}",
        ) from exc


@router.get(
    "/index/bm25/stats",
    response_model=BM25IndexStatsResponse,
    summary="Get BM25 Sparse Index Statistics",
    description="Returns operational statistics, vocabulary size, and chunk counts for BM25.",
    tags=["BM25 Sparse & Hybrid Search"],
)
def get_bm25_index_stats() -> BM25IndexStatsResponse:
    """Retrieve BM25 index diagnostic statistics."""
    return _bm25_indexing_service.get_index_stats()


# ==============================================================================
# Retrieval Evaluation, Cross-Encoder Reranking & Evidence Quality Endpoints (Session 07)
# ==============================================================================


@router.post(
    "/evaluation/retrieval/run",
    response_model=RetrievalEvaluationReport,
    summary="Run Information Retrieval Evaluation",
    description="Evaluates a retrieval method against a ground-truth dataset producing standard IR metrics.",
    tags=["Retrieval Evaluation & Evidence Quality"],
)
def run_retrieval_evaluation(
    request: RetrievalEvaluationRequest,
) -> RetrievalEvaluationReport:
    """Execute offline retrieval evaluation on benchmark queries."""
    dataset_file = (
        Path(request.dataset_path)
        if request.dataset_path
        else Path(_settings.RETRIEVAL_EVALUATION_DATASET)
    )
    if not dataset_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation dataset file not found: {dataset_file}",
        )

    try:
        queries = _evaluator.load_dataset(dataset_file)
        if request.ticker_filter:
            norm_ticker = request.ticker_filter.strip().upper()
            queries = [
                q for q in queries if q.ticker and q.ticker.upper() == norm_ticker
            ]

        if not queries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No queries found matching filter '{request.ticker_filter}'.",
            )

        # Define retriever adaptor based on request.retrieval_method
        method = request.retrieval_method.lower()

        if method == "dense":

            def retriever_adaptor(q, fetch_k):
                t0 = time.perf_counter()
                res = _semantic_search_service.search(
                    query=q.query,
                    ticker=q.ticker,
                    filing_type=q.filing_type,
                    section_identifier=q.section_identifier,
                    top_k=fetch_k,
                )
                return [r.chunk_id for r in res], (time.perf_counter() - t0) * 1000.0
        elif method == "sparse":

            def retriever_adaptor(q, fetch_k):
                t0 = time.perf_counter()
                res = _bm25_search_service.search(
                    query=q.query,
                    ticker=q.ticker,
                    filing_type=q.filing_type,
                    section_identifier=q.section_identifier,
                    top_k=fetch_k,
                )
                return [r.chunk_id for r in res], (time.perf_counter() - t0) * 1000.0
        elif method == "hybrid_reranked" or (method == "hybrid" and request.rerank):
            method = "hybrid_reranked"

            def retriever_adaptor(q, fetch_k):
                t0 = time.perf_counter()
                cand_pool = max(fetch_k, _settings.RERANKER_CANDIDATE_COUNT)
                h_res = _hybrid_search_service.search(
                    query=q.query,
                    ticker=q.ticker,
                    filing_type=q.filing_type,
                    section_identifier=q.section_identifier,
                    top_k=cand_pool,
                )
                reranked, _ = _reranker.rerank(
                    query=q.query,
                    candidates=h_res.results,
                    top_k=fetch_k,
                )
                return [r.chunk_id for r in reranked], (
                    time.perf_counter() - t0
                ) * 1000.0
        else:
            method = "hybrid"

            def retriever_adaptor(q, fetch_k):
                t0 = time.perf_counter()
                h_res = _hybrid_search_service.search(
                    query=q.query,
                    ticker=q.ticker,
                    filing_type=q.filing_type,
                    section_identifier=q.section_identifier,
                    top_k=fetch_k,
                )
                return [r.chunk_id for r in h_res.results], (
                    time.perf_counter() - t0
                ) * 1000.0

        dataset_type = (
            "curated"
            if any(q.dataset_type == "curated" for q in queries)
            else "synthetic"
        )
        report = _evaluator.evaluate_retriever(
            retriever_fn=retriever_adaptor,
            queries=queries,
            k=request.top_k,
            dataset_identifier=dataset_file.name,
            method_name=method,
            dataset_type=dataset_type,
        )

        _evaluation_reports[report.report_id] = report
        return report

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error executing retrieval evaluation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval evaluation failed: {exc}",
        ) from exc


@router.post(
    "/evaluation/retrieval/compare",
    response_model=RetrievalComparisonResponse,
    summary="Compare Retrieval Methods",
    description="Runs a fair comparative evaluation across Dense, Sparse, Hybrid, and Reranked search.",
    tags=["Retrieval Evaluation & Evidence Quality"],
)
def compare_retrieval_methods(
    request: RetrievalComparisonRequest,
) -> RetrievalComparisonResponse:
    """Execute fair multi-modal comparison over benchmark queries."""
    dataset_file = (
        Path(request.dataset_path)
        if request.dataset_path
        else Path(_settings.RETRIEVAL_EVALUATION_DATASET)
    )
    if not dataset_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation dataset file not found: {dataset_file}",
        )

    try:
        comparison_res = _comparator.compare_methods(
            dataset_path=dataset_file,
            top_k=request.top_k,
            include_reranking=request.include_reranking,
            ticker_filter=request.ticker_filter,
        )
        return comparison_res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error comparing retrieval methods: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval comparison failed: {exc}",
        ) from exc


@router.post(
    "/evaluation/evidence/validate",
    response_model=EvidenceValidationResult,
    summary="Validate Evidence Quality and Provenance",
    description="Validates statutory metadata completeness, SEC domains, duplicates, and period divergence.",
    tags=["Retrieval Evaluation & Evidence Quality"],
)
def validate_evidence(
    request: EvidenceValidationRequest,
) -> EvidenceValidationResult:
    """Validate retrieved evidence passages for provenance, duplicates, and temporal consistency."""
    try:
        candidates_to_validate: list[Any] = []

        if request.query and request.query.strip():
            # Retrieve fresh candidates
            method = request.retrieval_method.lower()
            if method == "dense":
                candidates_to_validate = _semantic_search_service.search(
                    query=request.query,
                    top_k=request.top_k,
                )
            elif method == "sparse":
                candidates_to_validate = _bm25_search_service.search(
                    query=request.query,
                    top_k=request.top_k,
                )
            else:
                resp = _hybrid_search_service.search(
                    query=request.query,
                    top_k=request.top_k,
                )
                candidates_to_validate = resp.results

        elif request.chunk_ids:
            # Query candidate chunks by ID from storage
            for c_id in request.chunk_ids:
                chunk = _doc_storage.get_chunk_with_provenance(c_id)
                if chunk is not None:
                    candidates_to_validate.append(chunk)
                else:
                    candidates_to_validate.append(
                        {
                            "chunk_id": c_id,
                            "chunk_text": "",
                            "source_url": "",
                        }
                    )

        return _evidence_validator.validate_chunks(candidates_to_validate)

    except Exception as exc:
        logger.error("Error validating evidence: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evidence validation failed: {exc}",
        ) from exc


@router.get(
    "/evaluation/retrieval/reports/{report_id}",
    response_model=RetrievalEvaluationReport,
    summary="Get Retrieval Evaluation Report",
    description="Retrieves a previously computed retrieval evaluation report by its unique report identifier.",
    tags=["Retrieval Evaluation & Evidence Quality"],
)
def get_retrieval_evaluation_report(
    report_id: str,
) -> RetrievalEvaluationReport:
    """Retrieve an evaluation report by ID."""
    report = _evaluation_reports.get(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retrieval evaluation report '{report_id}' not found.",
        )
    return report


@router.get(
    "/retrieval/reranker/status",
    response_model=RerankerStatusResponse,
    summary="Get Cross-Encoder Reranker Status",
    description="Returns configuration, model initialization status, compute device, and benchmark latency.",
    tags=["Retrieval Evaluation & Evidence Quality"],
)
def get_reranker_status() -> RerankerStatusResponse:
    """Retrieve operational status of the cross-encoder reranker."""
    return _reranker.get_status()


# =============================================================================
# Session 08: Evidence-Grounded Financial RAG & LLM Endpoints
# =============================================================================
@router.post(
    "/research/ask",
    response_model=RAGAnswer,
    summary="Ask Grounded Financial Research Question",
    description="Synthesize an evidence-backed financial research answer using retrieved SEC filing passages and deterministic calculation receipts.",
    tags=["Grounded Financial RAG & LLM"],
)
def ask_financial_question(request: RAGRequest) -> RAGAnswer:
    """Execute evidence-grounded RAG query."""
    try:
        return _rag_service.ask(request)
    except Exception as exc:
        logger.error("Error processing RAG request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query execution failed: {exc}",
        ) from exc


@router.get(
    "/research/answers/{answer_id}",
    response_model=RAGAnswer,
    summary="Get Stored Research Answer",
    description="Retrieve a previously generated financial research answer and its full provenance trail by answer_id.",
    tags=["Grounded Financial RAG & LLM"],
)
def get_research_answer(answer_id: str) -> RAGAnswer:
    """Fetch stored research answer by identifier."""
    answer = _rag_service.get_answer(answer_id)
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research answer '{answer_id}' not found.",
        )
    return answer


@router.get(
    "/llm/status",
    summary="Get LLM Provider Status",
    description="Inspect configured LLM provider, active model, reachability/health, and inference settings.",
    tags=["Grounded Financial RAG & LLM"],
)
def get_llm_status() -> dict[str, Any]:
    """Retrieve operational health and configuration of the LLM provider."""
    online = _llm_provider.health_check()
    return {
        "provider": _llm_provider.provider_name,
        "model": _llm_provider.model_name,
        "online": online,
        "base_url": getattr(_llm_provider, "base_url", None),
        "timeout": _settings.LLM_REQUEST_TIMEOUT,
        "temperature": _settings.LLM_TEMPERATURE,
        "max_tokens": _settings.LLM_MAX_TOKENS,
        "context_window": _settings.LLM_CONTEXT_WINDOW,
    }


@router.get(
    "/research/capabilities",
    response_model=RAGCapabilitiesResponse,
    summary="Get RAG System Capabilities",
    description="Expose supported retrieval modes, reranker availability, calculation integration, and LLM readiness.",
    tags=["Grounded Financial RAG & LLM"],
)
def get_research_capabilities() -> RAGCapabilitiesResponse:
    """Retrieve operational capabilities of the financial RAG system."""
    return _rag_service.get_capabilities()


# =============================================================================
# Session 09: Anti-Hallucination & Claim-Level Verification Endpoints
# =============================================================================
@router.get(
    "/research/answers/{answer_id}/verification",
    response_model=VerificationRun,
    summary="Get Claim Verification Run for Answer",
    description="Retrieve the latest claim-level anti-hallucination verification run and audit details for a specific research answer.",
    tags=["Anti-Hallucination & Verification"],
)
def get_answer_verification(answer_id: str) -> VerificationRun:
    """Fetch the latest verification run for an answer."""
    run = _verification_service.get_latest_verification_for_answer(answer_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run for answer '{answer_id}' not found.",
        )
    return run


@router.post(
    "/research/answers/{answer_id}/verify",
    response_model=VerificationRun,
    summary="Trigger Re-Verification of Research Answer",
    description="Execute an on-demand claim extraction and evidence verification audit on an existing research answer.",
    tags=["Anti-Hallucination & Verification"],
)
def verify_research_answer(answer_id: str) -> VerificationRun:
    """Execute claim verification on a stored research answer."""
    answer = _rag_service.get_answer(answer_id)
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research answer '{answer_id}' not found.",
        )
    try:
        run = _verification_service.verify_answer(
            answer_id=answer.answer_id,
            question=answer.question,
            answer_text=answer.answer,
            retrieved_evidence=answer.retrieved_evidence,
            calculation_evidence=answer.calculation_evidence,
            persist=True,
        )
        return run
    except Exception as exc:
        logger.error("Error running verification for answer %s: %s", answer_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {exc}",
        ) from exc
