"""Integration tests for FilingIngestionService."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

from backend.data.document_storage import DocumentStorage
from backend.data.filing_downloader import DownloadedFiling
from backend.data.filing_ingestion_service import FilingIngestionService
from backend.data.storage import Database
from tests.fixtures.sec_html_fixtures import SAMPLE_10K_HTML


def create_mocked_service(
    tmp_path: Path,
) -> tuple[FilingIngestionService, DocumentStorage]:
    """Create a FilingIngestionService with in-memory DB and mocked external components."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)

    # 1. Mock company_service
    company_service = MagicMock()
    company_service.get_company_by_ticker.return_value = {
        "ticker": "AAPL",
        "cik": "0000320193",
        "name": "Apple Inc.",
    }

    # 2. Mock sec_client
    sec_client = MagicMock()
    sec_client.get_company_filings.return_value = [
        {
            "accession_number": "0000320193-23-000106",
            "form": "10-K",
            "filing_date": "2023-11-03",
            "report_date": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        }
    ]

    # 3. Create local HTML file fixture
    file_path = tmp_path / "aapl-20230930.htm"
    file_path.write_text(SAMPLE_10K_HTML, encoding="utf-8")
    doc_hash = hashlib.sha256(SAMPLE_10K_HTML.encode("utf-8")).hexdigest()

    # 4. Mock downloader
    downloader = MagicMock()
    downloader.download_filing.return_value = DownloadedFiling(
        cik="0000320193",
        ticker="AAPL",
        accession_number="0000320193-23-000106",
        form="10-K",
        primary_document="aapl-20230930.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        local_file_path=file_path,
        file_size_bytes=len(SAMPLE_10K_HTML),
        document_hash=doc_hash,
        is_cached=False,
    )

    service = FilingIngestionService(
        company_service=company_service,
        sec_client=sec_client,
        downloader=downloader,
        document_storage=doc_storage,
        db=db,
    )

    return service, doc_storage


def test_ingest_filing_happy_path(tmp_path: Path) -> None:
    """Verify end-to-end ingestion downloads, parses, extracts sections, chunks, and persists."""
    service, storage = create_mocked_service(tmp_path)

    result = service.ingest_filing(
        ticker="AAPL",
        accession_number="0000320193-23-000106",
    )

    assert result.processing_status == "completed"
    assert result.ticker == "AAPL"
    assert result.accession_number == "0000320193-23-000106"
    assert "ITEM_1" in result.sections_extracted
    assert "ITEM_1A" in result.sections_extracted
    assert "ITEM_7" in result.sections_extracted
    assert "ITEM_7A" in result.sections_extracted
    assert result.total_chunks > 0

    # Verify persisted document
    doc = storage.get_document_by_accession("0000320193-23-000106")
    assert doc is not None
    assert doc["processing_status"] == "completed"

    # Verify persisted chunks
    chunks = storage.get_chunks_for_document(doc["document_id"])
    assert len(chunks) == result.total_chunks
    assert all(c["ticker"] == "AAPL" for c in chunks)


def test_ingest_filing_already_ingested(tmp_path: Path) -> None:
    """Verify second ingestion call without force_refresh returns already_ingested."""
    service, _ = create_mocked_service(tmp_path)

    # First run
    res1 = service.ingest_filing("AAPL", "0000320193-23-000106")
    assert res1.processing_status == "completed"

    # Second run without force_refresh
    res2 = service.ingest_filing("AAPL", "0000320193-23-000106", force_refresh=False)
    assert res2.processing_status == "already_ingested"
    assert res2.total_chunks == res1.total_chunks
    assert any("previously ingested" in w for w in res2.warnings)


def test_ingest_filing_force_refresh(tmp_path: Path) -> None:
    """Verify force_refresh=True re-downloads and reprocesses document."""
    service, _storage = create_mocked_service(tmp_path)

    # First run
    res1 = service.ingest_filing("AAPL", "0000320193-23-000106")
    assert res1.processing_status == "completed"

    # Second run with force_refresh
    res2 = service.ingest_filing("AAPL", "0000320193-23-000106", force_refresh=True)
    assert res2.processing_status == "completed"
    assert res2.total_chunks == res1.total_chunks


def test_ingest_filing_unknown_company(tmp_path: Path) -> None:
    """Verify unknown ticker returns failed status with clear error."""
    service, _ = create_mocked_service(tmp_path)
    service.company_service.get_company_by_ticker.return_value = None

    result = service.ingest_filing("UNKNOWN", "0000320193-23-000106")
    assert result.processing_status == "failed"
    assert "not found" in (result.error or "").lower()


def test_ingest_filing_accession_not_found(tmp_path: Path) -> None:
    """Verify invalid accession returns failed status."""
    service, _ = create_mocked_service(tmp_path)

    result = service.ingest_filing("AAPL", "9999999999-99-999999")
    assert result.processing_status == "failed"
    assert "not found" in (result.error or "").lower()


def test_ingest_filing_download_failure(tmp_path: Path) -> None:
    """Verify download error is trapped and marked failed in DB."""
    service, storage = create_mocked_service(tmp_path)
    service.downloader.download_filing.side_effect = RuntimeError(
        "Simulated network timeout"
    )

    result = service.ingest_filing("AAPL", "0000320193-23-000106")
    assert result.processing_status == "failed"
    assert "Download failed" in (result.error or "")

    # Document should be recorded as failed
    doc = storage.get_document_by_accession("0000320193-23-000106")
    assert doc is not None
    assert doc["processing_status"] == "failed"
