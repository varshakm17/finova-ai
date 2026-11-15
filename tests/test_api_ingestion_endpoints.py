"""Tests for document ingestion API endpoints in backend/api/routes.py."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.data.filing_ingestion_service import IngestionResult
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_ingest_filing_endpoint_success(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/filings/{accession}/ingest returns 200 on success."""
    mock_result = IngestionResult(
        document_id="0000320193_000032019323000106",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        processing_status="completed",
        sections_extracted=["ITEM_1", "ITEM_1A", "ITEM_7", "ITEM_7A"],
        sections_not_found=[],
        total_chunks=14,
        document_hash="hash123",
        file_size_bytes=50000,
        warnings=[],
    )

    with patch("backend.api.routes._ingestion_service.ingest_filing") as mock_ingest:
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/companies/AAPL/filings/0000320193-23-000106/ingest"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["accession_number"] == "0000320193-23-000106"
        assert data["processing_status"] == "completed"
        assert len(data["sections_extracted"]) == 4
        assert data["total_chunks"] == 14


def test_ingest_filing_endpoint_already_ingested(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/filings/{accession}/ingest returns already_ingested."""
    mock_result = IngestionResult(
        document_id="0000320193_000032019323000106",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        processing_status="already_ingested",
        sections_extracted=["ITEM_1"],
        total_chunks=5,
        warnings=["Document was previously ingested."],
    )

    with patch("backend.api.routes._ingestion_service.ingest_filing") as mock_ingest:
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/companies/AAPL/filings/0000320193-23-000106/ingest"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["processing_status"] == "already_ingested"
        assert len(data["warnings"]) > 0


def test_ingest_filing_endpoint_force_refresh(client: TestClient) -> None:
    """Verify force_refresh query param is passed to service."""
    mock_result = IngestionResult(
        document_id="0000320193_000032019323000106",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        accession_number="0000320193-23-000106",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        processing_status="completed",
        sections_extracted=["ITEM_1"],
        total_chunks=8,
    )

    with patch("backend.api.routes._ingestion_service.ingest_filing") as mock_ingest:
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/companies/AAPL/filings/0000320193-23-000106/ingest?force_refresh=true"
        )
        assert response.status_code == 200
        mock_ingest.assert_called_once_with(
            ticker="AAPL",
            accession_number="0000320193-23-000106",
            force_refresh=True,
        )


def test_ingest_filing_endpoint_not_found(client: TestClient) -> None:
    """Verify POST returns 404 when company or filing is not found."""
    mock_result = IngestionResult(
        document_id="",
        ticker="XYZ",
        cik="",
        company_name="",
        accession_number="0000320193-23-000106",
        filing_type="",
        filing_date="",
        report_date=None,
        processing_status="failed",
        error="Company with ticker 'XYZ' not found in SEC directory.",
    )

    with patch("backend.api.routes._ingestion_service.ingest_filing") as mock_ingest:
        mock_ingest.return_value = mock_result

        response = client.post(
            "/api/v1/companies/XYZ/filings/0000320193-23-000106/ingest"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()


def test_list_documents_endpoint_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/documents returns list of ingested documents."""
    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker"
        ) as mock_lookup,
        patch(
            "backend.api.routes._doc_storage.list_documents_for_company"
        ) as mock_list,
    ):
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_list.return_value = [
            {
                "document_id": "0000320193_accn1",
                "cik": "0000320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "accession_number": "0000320193-23-000106",
                "filing_type": "10-K",
                "filing_date": "2023-11-03",
                "report_date": "2023-09-30",
                "primary_document": "aapl-20230930.htm",
                "source_url": "https://sec.gov",
                "processing_status": "completed",
                "document_hash": "hash1",
                "created_at": "2023-11-04T00:00:00Z",
                "updated_at": "2023-11-04T00:00:00Z",
            }
        ]

        response = client.get("/api/v1/companies/AAPL/documents")
        assert response.status_code == 200
        docs = response.json()
        assert len(docs) == 1
        assert docs[0]["accession_number"] == "0000320193-23-000106"
        assert docs[0]["filing_type"] == "10-K"


def test_list_documents_endpoint_with_filing_type_filter(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/documents passes filing_type to storage."""
    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker"
        ) as mock_lookup,
        patch(
            "backend.api.routes._doc_storage.list_documents_for_company"
        ) as mock_list,
    ):
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_list.return_value = []

        response = client.get("/api/v1/companies/AAPL/documents?filing_type=10-K")
        assert response.status_code == 200
        mock_list.assert_called_once_with(ticker_or_cik="AAPL", filing_type="10-K")


def test_list_documents_endpoint_unknown_company(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/documents returns 404 for unknown ticker."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker"
    ) as mock_lookup:
        mock_lookup.return_value = None

        response = client.get("/api/v1/companies/UNKNOWN/documents")
        assert response.status_code == 404


def test_get_document_details_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/documents/{accession} returns details with sections."""
    doc_payload = {
        "document_id": "0000320193_accn1",
        "cik": "0000320193",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "accession_number": "0000320193-23-000106",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "report_date": "2023-09-30",
        "primary_document": "aapl-20230930.htm",
        "source_url": "https://sec.gov",
        "processing_status": "completed",
        "document_hash": "hash1",
        "created_at": "2023-11-04T00:00:00Z",
        "updated_at": "2023-11-04T00:00:00Z",
    }
    sections_payload = [
        {
            "section_id": "sec1",
            "document_id": "0000320193_accn1",
            "section_identifier": "ITEM_1",
            "section_title": "Item 1. Business",
            "extraction_status": "extracted",
            "char_count": 500,
            "start_char": 0,
            "end_char": 500,
            "created_at": "2023-11-04T00:00:00Z",
        }
    ]

    with (
        patch("backend.api.routes._doc_storage.get_document_by_accession") as mock_doc,
        patch("backend.api.routes._doc_storage.get_sections_for_document") as mock_sec,
        patch("backend.api.routes._doc_storage.get_chunks_for_document") as mock_chunks,
    ):
        mock_doc.return_value = doc_payload
        mock_sec.return_value = sections_payload
        mock_chunks.return_value = [{"chunk_id": "c1"}]

        response = client.get("/api/v1/companies/AAPL/documents/0000320193-23-000106")
        assert response.status_code == 200
        data = response.json()
        assert data["accession_number"] == "0000320193-23-000106"
        assert len(data["sections"]) == 1
        assert data["total_chunks"] == 1


def test_get_document_details_not_found(client: TestClient) -> None:
    """Verify GET document details returns 404 when document does not exist."""
    with patch("backend.api.routes._doc_storage.get_document_by_accession") as mock_doc:
        mock_doc.return_value = None

        response = client.get("/api/v1/companies/AAPL/documents/nonexistent-accn")
        assert response.status_code == 404


def test_get_document_chunks_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/documents/{accession}/chunks returns chunks."""
    doc_payload = {
        "document_id": "0000320193_accn1",
        "accession_number": "0000320193-23-000106",
    }
    chunks_payload = [
        {
            "chunk_id": "c1",
            "document_id": "0000320193_accn1",
            "section_id": "sec1",
            "ticker": "AAPL",
            "accession_number": "0000320193-23-000106",
            "filing_type": "10-K",
            "section_identifier": "ITEM_1A",
            "section_title": "Item 1A. Risk Factors",
            "chunk_index": 0,
            "chunk_text": "Chunk text content.",
            "start_offset": 0,
            "end_offset": 50,
            "char_count": 50,
            "source_url": "https://sec.gov",
            "created_at": "2023-11-04T00:00:00Z",
        }
    ]

    with (
        patch("backend.api.routes._doc_storage.get_document_by_accession") as mock_doc,
        patch("backend.api.routes._doc_storage.get_chunks_for_document") as mock_chunks,
    ):
        mock_doc.return_value = doc_payload
        mock_chunks.return_value = chunks_payload

        response = client.get(
            "/api/v1/companies/AAPL/documents/0000320193-23-000106/chunks?section_identifier=ITEM_1A"
        )
        assert response.status_code == 200
        chunks = response.json()
        assert len(chunks) == 1
        assert chunks[0]["section_identifier"] == "ITEM_1A"
        mock_chunks.assert_called_once_with(
            document_id="0000320193_accn1",
            section_identifier="ITEM_1A",
        )


def test_get_document_chunks_not_found(client: TestClient) -> None:
    """Verify GET chunks returns 404 when document does not exist."""
    with patch("backend.api.routes._doc_storage.get_document_by_accession") as mock_doc:
        mock_doc.return_value = None

        response = client.get(
            "/api/v1/companies/AAPL/documents/nonexistent-accn/chunks"
        )
        assert response.status_code == 404
