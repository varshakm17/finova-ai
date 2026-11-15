"""Financial data extraction, SEC EDGAR client, and parsing pipelines for Finova AI."""

from backend.data.chunker import DocumentChunk, SectionChunker
from backend.data.company_service import CompanyService, normalize_ticker
from backend.data.data_normalizer import FinancialObservation, deduplicate_observations
from backend.data.document_storage import DocumentStorage
from backend.data.filing_downloader import DownloadedFiling, FilingDownloader
from backend.data.filing_ingestion_service import (
    FilingIngestionService,
    IngestionResult,
)
from backend.data.financial_extractor import FinancialExtractor
from backend.data.html_parser import HTMLDocumentParser
from backend.data.sec_client import (
    SECAuthenticationError,
    SECClient,
    SECConfigurationError,
    SECError,
    SECNetworkError,
    SECNotFoundError,
    SECRateLimitError,
    normalize_cik,
)
from backend.data.section_extractor import ExtractedSection, SectionExtractor
from backend.data.storage import Database

__all__ = [
    "CompanyService",
    "Database",
    "DocumentChunk",
    "DocumentStorage",
    "DownloadedFiling",
    "ExtractedSection",
    "FilingDownloader",
    "FilingIngestionService",
    "FinancialExtractor",
    "FinancialObservation",
    "HTMLDocumentParser",
    "IngestionResult",
    "SECAuthenticationError",
    "SECClient",
    "SECConfigurationError",
    "SECError",
    "SECNetworkError",
    "SECNotFoundError",
    "SECRateLimitError",
    "SectionChunker",
    "SectionExtractor",
    "deduplicate_observations",
    "normalize_cik",
    "normalize_ticker",
]
