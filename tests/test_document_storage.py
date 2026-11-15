"""Unit tests for DocumentStorage."""

from backend.data.chunker import DocumentChunk
from backend.data.document_storage import DocumentStorage
from backend.data.section_extractor import ExtractedSection
from backend.data.storage import Database


def get_test_storage() -> tuple[DocumentStorage, Database]:
    """Create in-memory Database and DocumentStorage with company seed."""
    db = Database(db_path=":memory:")
    storage = DocumentStorage(db=db)
    # Seed company to satisfy foreign key
    db.save_company({"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."})
    return storage, db


def test_save_and_get_document() -> None:
    """Verify document metadata can be saved, updated, and retrieved by accession number."""
    storage, _ = get_test_storage()

    doc_data = {
        "document_id": "0000320193_000032019323000106",
        "cik": "0000320193",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "accession_number": "0000320193-23-000106",
        "filing_type": "10-K",
        "filing_date": "2023-11-03",
        "report_date": "2023-09-30",
        "primary_document": "aapl-20230930.htm",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
        "local_file_path": "datasets/filings/0000320193/0000320193-23-000106/aapl-20230930.htm",
        "processing_status": "downloaded",
        "document_hash": "abc123hash",
        "error_message": None,
    }

    doc_id = storage.save_document(doc_data)
    assert doc_id == doc_data["document_id"]

    retrieved = storage.get_document_by_accession("0000320193-23-000106")
    assert retrieved is not None
    assert retrieved["ticker"] == "AAPL"
    assert retrieved["filing_type"] == "10-K"
    assert retrieved["processing_status"] == "downloaded"

    # Update status
    storage.update_document_status(doc_id, "completed")
    updated = storage.get_document_by_accession("0000320193-23-000106")
    assert updated is not None
    assert updated["processing_status"] == "completed"


def test_list_documents_for_company() -> None:
    """Verify listing documents by ticker/CIK with optional filing type filtering."""
    storage, _ = get_test_storage()

    for accn, form in [("accn-1", "10-K"), ("accn-2", "10-Q"), ("accn-3", "10-K")]:
        storage.save_document(
            {
                "document_id": f"0000320193_{accn}",
                "cik": "0000320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "accession_number": accn,
                "filing_type": form,
                "filing_date": "2023-11-03",
                "report_date": "2023-09-30",
                "primary_document": "doc.htm",
                "source_url": "https://sec.gov/doc.htm",
                "local_file_path": "path/doc.htm",
                "processing_status": "completed",
                "document_hash": "hash",
            }
        )

    # All filings
    all_docs = storage.list_documents_for_company("AAPL")
    assert len(all_docs) == 3

    # Filtered by 10-K
    ten_k_docs = storage.list_documents_for_company("AAPL", filing_type="10-K")
    assert len(ten_k_docs) == 2

    # Filtered by 10-Q
    ten_q_docs = storage.list_documents_for_company("AAPL", filing_type="10-Q")
    assert len(ten_q_docs) == 1


def test_save_and_get_sections() -> None:
    """Verify extracted sections can be saved and retrieved for a document."""
    storage, _ = get_test_storage()

    doc_id = "0000320193_accn1"
    storage.save_document(
        {
            "document_id": doc_id,
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "accession_number": "accn-1",
            "filing_type": "10-K",
            "filing_date": "2023-11-03",
            "primary_document": "doc.htm",
            "source_url": "https://sec.gov/doc.htm",
            "local_file_path": "path/doc.htm",
            "processing_status": "completed",
            "document_hash": "hash",
        }
    )

    sections = [
        ExtractedSection(
            section_identifier="ITEM_1",
            section_title="Item 1. Business",
            status="extracted",
            text="Business text here...",
            char_count=19,
            start_char=100,
            end_char=119,
        ),
        ExtractedSection(
            section_identifier="ITEM_1A",
            section_title="Item 1A. Risk Factors",
            status="extracted",
            text="Risk factors text here...",
            char_count=25,
            start_char=120,
            end_char=145,
        ),
    ]

    count = storage.save_sections(doc_id, sections)
    assert count == 2

    saved_sections = storage.get_sections_for_document(doc_id)
    assert len(saved_sections) == 2
    sec_ids = [s["section_identifier"] for s in saved_sections]
    assert "ITEM_1" in sec_ids
    assert "ITEM_1A" in sec_ids


def test_save_and_get_chunks() -> None:
    """Verify chunks can be saved and filtered by section_identifier."""
    storage, _ = get_test_storage()

    doc_id = "0000320193_accn1"
    storage.save_document(
        {
            "document_id": doc_id,
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "accession_number": "accn-1",
            "filing_type": "10-K",
            "filing_date": "2023-11-03",
            "primary_document": "doc.htm",
            "source_url": "https://sec.gov/doc.htm",
            "local_file_path": "path/doc.htm",
            "processing_status": "completed",
            "document_hash": "hash",
        }
    )

    storage.save_sections(
        doc_id,
        [
            ExtractedSection("ITEM_1", "Item 1", "extracted", "text", 4, 0, 4),
            ExtractedSection("ITEM_7", "Item 7", "extracted", "text", 4, 5, 9),
        ],
    )

    chunks = [
        DocumentChunk(
            company_ticker="AAPL",
            company_cik="0000320193",
            company_name="Apple Inc.",
            accession_number="accn-1",
            filing_type="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            section_identifier="ITEM_1",
            section_title="Item 1",
            chunk_index=0,
            source_url="https://sec.gov",
            start_offset=0,
            end_offset=50,
            char_count=50,
            chunk_text="Chunk 0 from Item 1",
        ),
        DocumentChunk(
            company_ticker="AAPL",
            company_cik="0000320193",
            company_name="Apple Inc.",
            accession_number="accn-1",
            filing_type="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            section_identifier="ITEM_1",
            section_title="Item 1",
            chunk_index=1,
            source_url="https://sec.gov",
            start_offset=40,
            end_offset=90,
            char_count=50,
            chunk_text="Chunk 1 from Item 1",
        ),
        DocumentChunk(
            company_ticker="AAPL",
            company_cik="0000320193",
            company_name="Apple Inc.",
            accession_number="accn-1",
            filing_type="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            section_identifier="ITEM_7",
            section_title="Item 7",
            chunk_index=0,
            source_url="https://sec.gov",
            start_offset=100,
            end_offset=150,
            char_count=50,
            chunk_text="Chunk 0 from Item 7",
        ),
    ]

    saved_count = storage.save_chunks(doc_id, chunks)
    assert saved_count == 3

    # All chunks for document
    all_chunks = storage.get_chunks_for_document(doc_id)
    assert len(all_chunks) == 3

    # Filtered by ITEM_1
    item_1_chunks = storage.get_chunks_for_document(doc_id, section_identifier="ITEM_1")
    assert len(item_1_chunks) == 2

    # Filtered by ITEM_7
    item_7_chunks = storage.get_chunks_for_document(doc_id, section_identifier="ITEM_7")
    assert len(item_7_chunks) == 1


def test_delete_document_and_cascading_children() -> None:
    """Verify deleting a document cascades to delete its sections and chunks."""
    storage, _ = get_test_storage()

    doc_id = "0000320193_accn-del"
    storage.save_document(
        {
            "document_id": doc_id,
            "cik": "0000320193",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "accession_number": "accn-del",
            "filing_type": "10-K",
            "filing_date": "2023-11-03",
            "primary_document": "doc.htm",
            "source_url": "https://sec.gov/doc.htm",
            "local_file_path": "path/doc.htm",
            "processing_status": "completed",
            "document_hash": "hash",
        }
    )

    storage.save_sections(
        doc_id,
        [ExtractedSection("ITEM_1", "Item 1", "extracted", "text", 4, 0, 4)],
    )

    storage.save_chunks(
        doc_id,
        [
            DocumentChunk(
                company_ticker="AAPL",
                company_cik="0000320193",
                company_name="Apple Inc.",
                accession_number="accn-del",
                filing_type="10-K",
                filing_date="2023-11-03",
                report_date="2023-09-30",
                section_identifier="ITEM_1",
                section_title="Item 1",
                chunk_index=0,
                source_url="https://sec.gov",
                start_offset=0,
                end_offset=4,
                char_count=4,
                chunk_text="text",
            )
        ],
    )

    assert storage.get_document_by_accession("accn-del") is not None
    assert len(storage.get_sections_for_document(doc_id)) == 1
    assert len(storage.get_chunks_for_document(doc_id)) == 1

    deleted = storage.delete_document_and_chunks("accn-del")
    assert deleted is True

    assert storage.get_document_by_accession("accn-del") is None
    assert len(storage.get_sections_for_document(doc_id)) == 0
    assert len(storage.get_chunks_for_document(doc_id)) == 0
