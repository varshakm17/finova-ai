"""Unit and integration tests for BM25Index and BM25SearchService.

Verifies index construction, persistent JSON reload, empty corpus handling,
keyword scoring, chunk deletion, and metadata-filtered search.
"""

from pathlib import Path

import pytest

from backend.data.chunker import DocumentChunk
from backend.data.document_storage import DocumentStorage
from backend.data.section_extractor import ExtractedSection
from backend.data.storage import Database
from backend.retrieval.bm25_search import (
    BM25Index,
    BM25SearchService,
    FinancialTokenizer,
)


def seed_test_chunks(storage: DocumentStorage) -> list[str]:
    """Helper to seed test documents and chunks into a test database."""
    storage.db.save_company(
        {"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."}
    )
    storage.db.save_company(
        {"cik": "0000789019", "ticker": "MSFT", "name": "Microsoft Corporation"}
    )

    # Apple 10-K
    aapl_doc = {
        "document_id": "doc_aapl_10k_2023",
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
        "processing_status": "completed",
        "document_hash": "hash_aapl",
    }
    storage.save_document(aapl_doc)
    storage.save_sections(
        aapl_doc["document_id"],
        [
            ExtractedSection(
                section_identifier="ITEM_1A",
                section_title="Item 1A. Risk Factors",
                status="extracted",
                start_char=0,
                end_char=500,
                char_count=500,
                text="Supply chain disruptions in Asia and component shortages could adversely impact revenue.",
            ),
            ExtractedSection(
                section_identifier="ITEM_7",
                section_title="Item 7. MD&A",
                status="extracted",
                start_char=501,
                end_char=1000,
                char_count=500,
                text="Operating cash-flow increased year-over-year to $110 billion with strong liquidity.",
            ),
        ],
    )
    storage.save_chunks(
        aapl_doc["document_id"],
        [
            DocumentChunk(
                company_ticker="AAPL",
                company_cik="0000320193",
                company_name="Apple Inc.",
                accession_number="0000320193-23-000106",
                filing_type="10-K",
                filing_date="2023-11-03",
                report_date="2023-09-30",
                section_identifier="ITEM_1A",
                section_title="Item 1A. Risk Factors",
                chunk_index=0,
                chunk_text="Global supply chain disruptions and semiconductor shortages in Asia could adversely affect operations and quarterly revenue.",
                start_offset=0,
                end_offset=120,
                char_count=120,
                source_url="https://www.sec.gov/aapl",
            ),
            DocumentChunk(
                company_ticker="AAPL",
                company_cik="0000320193",
                company_name="Apple Inc.",
                accession_number="0000320193-23-000106",
                filing_type="10-K",
                filing_date="2023-11-03",
                report_date="2023-09-30",
                section_identifier="ITEM_7",
                section_title="Item 7. MD&A",
                chunk_index=0,
                chunk_text="Operating cash-flow increased year-over-year to $110 billion supported by non-GAAP efficiency and cash management.",
                start_offset=0,
                end_offset=115,
                char_count=115,
                source_url="https://www.sec.gov/aapl",
            ),
        ],
    )

    # Microsoft 10-K
    msft_doc = {
        "document_id": "doc_msft_10k_2023",
        "cik": "0000789019",
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "accession_number": "0000789019-23-000050",
        "filing_type": "10-K",
        "filing_date": "2023-07-28",
        "report_date": "2023-06-30",
        "primary_document": "msft-20230630.htm",
        "source_url": "https://www.sec.gov/msft",
        "local_file_path": "datasets/filings/msft.htm",
        "processing_status": "completed",
        "document_hash": "hash_msft",
    }
    storage.save_document(msft_doc)
    storage.save_sections(
        msft_doc["document_id"],
        [
            ExtractedSection(
                section_identifier="ITEM_1A",
                section_title="Item 1A. Risk Factors",
                status="extracted",
                start_char=0,
                end_char=500,
                char_count=500,
                text="Cybersecurity threats and cloud computing platform outages pose operational risks.",
            ),
        ],
    )
    storage.save_chunks(
        msft_doc["document_id"],
        [
            DocumentChunk(
                company_ticker="MSFT",
                company_cik="0000789019",
                company_name="Microsoft Corporation",
                accession_number="0000789019-23-000050",
                filing_type="10-K",
                filing_date="2023-07-28",
                report_date="2023-06-30",
                section_identifier="ITEM_1A",
                section_title="Item 1A. Risk Factors",
                chunk_index=0,
                chunk_text="Cybersecurity breaches, data center disruptions, and cloud service availability are critical enterprise operational risks.",
                start_offset=0,
                end_offset=125,
                char_count=125,
                source_url="https://www.sec.gov/msft",
            ),
        ],
    )
    aapl_chunks = storage.get_chunks_for_ticker("AAPL")
    msft_chunks = storage.get_chunks_for_ticker("MSFT")
    return [c["chunk_id"] for c in aapl_chunks] + [c["chunk_id"] for c in msft_chunks]


def test_bm25_index_empty_corpus(tmp_path: Path) -> None:
    """Verify BM25Index handles empty corpus safely without ZeroDivisionError."""
    index = BM25Index(index_dir=tmp_path)
    assert index.total_chunks == 0
    # Search on empty index
    results = index.search(["supply", "chain"])
    assert results == []


def test_bm25_index_build_search_and_ranking(tmp_path: Path) -> None:
    """Verify building an index from chunks, scoring, and ranking."""
    index = BM25Index(index_dir=tmp_path)
    chunks = [
        ("c1", "Supply chain disruptions and semiconductor shortages in Asia.", "h1"),
        ("c2", "Operating cash-flow increased year-over-year to $110 billion.", "h2"),
        ("c3", "Cloud computing and cybersecurity operational risks.", "h3"),
    ]
    index.build_from_chunks(chunks)
    assert index.total_chunks == 3

    # Search for supply chain
    tok = FinancialTokenizer()
    matches = index.search(tok.tokenize("supply chain shortages"), top_k=5)
    assert len(matches) > 0
    # Top match should be c1
    top_id, top_score = matches[0]
    assert top_id == "c1"
    assert top_score > 0.0

    # Search for cash flow
    matches_cf = index.search(tok.tokenize("operating cash-flow billion"), top_k=5)
    assert len(matches_cf) > 0
    assert matches_cf[0][0] == "c2"


def test_bm25_index_persistence_and_reload(tmp_path: Path) -> None:
    """Verify saving to JSON and reloading preserves the exact same search behavior."""
    index = BM25Index(index_dir=tmp_path)
    chunks = [
        ("doc_1", "Revenue grew 15.4% year-over-year.", "h1"),
        ("doc_2", "Debt-to-equity ratio was 0.85.", "h2"),
    ]
    index.build_from_chunks(chunks)

    # Re-instantiate another index pointing to the same directory
    loaded_index = BM25Index(index_dir=tmp_path)
    assert loaded_index.total_chunks == 2

    tok = FinancialTokenizer()
    res = loaded_index.search(tok.tokenize("revenue year-over-year"), top_k=2)
    assert len(res) == 1
    assert res[0][0] == "doc_1"


def test_bm25_index_chunk_removal_and_update(tmp_path: Path) -> None:
    """Verify updating a chunk and removing a chunk."""
    index = BM25Index(index_dir=tmp_path)
    index.add_or_update_chunk("c1", "Initial text about revenue.", "h1")
    index.add_or_update_chunk("c2", "Text about expenses.", "h2")
    index.rebuild_bm25_model()
    assert index.total_chunks == 2

    # Update c1
    index.add_or_update_chunk("c1", "Updated text about profit margins.", "h1_new")
    index.rebuild_bm25_model()
    assert index.total_chunks == 2

    tok = FinancialTokenizer()
    matches = index.search(tok.tokenize("profit margins"))
    assert len(matches) == 1
    assert matches[0][0] == "c1"

    # Remove c2
    assert index.remove_chunk("c2") is True
    assert index.remove_chunk("nonexistent") is False
    index.rebuild_bm25_model()
    assert index.total_chunks == 1


def test_bm25_search_service_provenance_and_filters(tmp_path: Path) -> None:
    """Verify BM25SearchService resolves provenance and respects metadata filters."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    chunk_ids = seed_test_chunks(storage)
    aapl_risk_id = chunk_ids[0]
    aapl_mda_id = chunk_ids[1]
    msft_risk_id = chunk_ids[2]

    # Build BM25 index with the 3 chunks
    chunks_data = [
        (
            aapl_risk_id,
            "Global supply chain disruptions and semiconductor shortages in Asia.",
            "h1",
        ),
        (
            aapl_mda_id,
            "Operating cash-flow increased year-over-year to $110 billion.",
            "h2",
        ),
        (
            msft_risk_id,
            "Cybersecurity breaches, data center disruptions, and cloud service availability.",
            "h3",
        ),
    ]
    bm25_idx = BM25Index(index_dir=tmp_path / "idx")
    bm25_idx.build_from_chunks(chunks_data)

    service = BM25SearchService(
        document_storage=storage,
        bm25_index=bm25_idx,
    )

    # 1. Search without filters
    results = service.search(query="supply chain disruptions", top_k=5)
    assert len(results) >= 1
    top = results[0]
    assert top.chunk_id == aapl_risk_id
    assert top.ticker == "AAPL"
    assert top.company_name == "Apple Inc."
    assert top.section_identifier == "ITEM_1A"
    assert "supply" in top.matched_terms

    # 2. Search with company filter matching
    res_aapl = service.search(query="disruptions", ticker="AAPL", top_k=5)
    assert all(r.ticker == "AAPL" for r in res_aapl)

    # 3. Search with company filter non-matching
    res_msft = service.search(query="supply chain", ticker="MSFT", top_k=5)
    assert len(res_msft) == 0

    # 4. Search with section filter
    res_mda = service.search(query="disruptions", section_identifier="ITEM_7", top_k=5)
    assert all(r.section_identifier == "ITEM_7" for r in res_mda)

    # 5. Invalid query raises ValueError
    with pytest.raises(ValueError, match="cannot be empty"):
        service.search(query="   ")
