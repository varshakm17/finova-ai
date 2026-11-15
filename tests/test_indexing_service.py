"""Integration tests for IndexingService."""

from pathlib import Path

import numpy as np

from backend.data.chunker import DocumentChunk
from backend.data.document_storage import DocumentStorage
from backend.data.section_extractor import ExtractedSection
from backend.data.storage import Database
from backend.retrieval.embedding_service import EmbeddingService
from backend.retrieval.indexing_service import IndexingService
from backend.retrieval.vector_store import NumpyVectorStore


def seed_synthetic_chunks(doc_storage: DocumentStorage) -> None:
    """Helper seeding synthetic document and chunks for AAPL in SQLite."""
    # 1. Company
    doc_storage.db.save_company(
        {"cik": "0000320193", "ticker": "AAPL", "name": "Apple Inc."}
    )

    # 2. Document
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
        "local_file_path": "datasets/filings/0000320193/0000320193-23-000106/primary.htm",
        "processing_status": "completed",
        "document_hash": "mock_hash_123",
        "error_message": None,
    }
    doc_storage.save_document(doc_data)

    # 3. Sections
    sec_1a = ExtractedSection(
        section_identifier="ITEM_1A",
        section_title="Item 1A. Risk Factors",
        status="found",
        char_count=500,
        start_char=0,
        end_char=500,
        text="Global supply chains and manufacturing concentrations present material business risks.",
    )
    sec_7 = ExtractedSection(
        section_identifier="ITEM_7",
        section_title="Item 7. MD&A",
        status="found",
        char_count=600,
        start_char=500,
        end_char=1100,
        text="Total net sales decreased 2.8% to $383.3 billion during fiscal 2023.",
    )
    doc_storage.save_sections(doc_data["document_id"], [sec_1a, sec_7])

    # 4. Chunks
    chunk1 = DocumentChunk(
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
        source_url=doc_data["source_url"],
        start_offset=0,
        end_offset=86,
        char_count=86,
        chunk_text="Global supply chains and manufacturing concentrations present material business risks.",
    )
    chunk2 = DocumentChunk(
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
        source_url=doc_data["source_url"],
        start_offset=0,
        end_offset=68,
        char_count=68,
        chunk_text="Total net sales decreased 2.8% to $383.3 billion during fiscal 2023.",
    )
    doc_storage.save_chunks(doc_data["document_id"], [chunk1, chunk2])


def make_deterministic_mock_encoder(dim: int = 384):
    """Returns a deterministic mock encoder that generates synthetic vectors."""

    def encoder(texts: list[str]) -> np.ndarray:
        vecs = []
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            # Embed based on presence of keywords
            if "supply" in text.lower() or "risk" in text.lower():
                vec[0] = 1.0
            if "sales" in text.lower() or "revenue" in text.lower():
                vec[1] = 1.0
            # Ensure non-zero
            vec[dim - 1] = 0.1
            vecs.append(vec)
        return np.array(vecs, dtype=np.float32)

    return encoder


def test_indexing_service_incremental_workflow(tmp_path: Path) -> None:
    """Verify initial indexing, duplicate skip, content update detection, and rebuild."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)
    seed_synthetic_chunks(doc_storage)

    mock_encoder = make_deterministic_mock_encoder(dim=384)
    emb_service = EmbeddingService(
        model_name="test-model",
        dimension=384,
        encoder_fn=mock_encoder,
    )
    vector_store = NumpyVectorStore(dimension=384, index_dir=tmp_path)

    service = IndexingService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )

    # 1. First run: should index both chunks
    summary1 = service.index_company_chunks(ticker="AAPL")
    assert summary1.total_discovered == 2
    assert summary1.newly_indexed == 2
    assert summary1.already_indexed == 0
    assert summary1.failed == 0
    assert vector_store.get_index_stats()["total_vectors"] == 2

    # 2. Status inspection
    status = service.get_indexing_status("AAPL")
    assert status.total_available_chunks == 2
    assert status.indexed_chunks == 2
    assert status.pending_chunks == 0
    assert status.failed_chunks == 0

    # 3. Second run without changes: should skip both
    summary2 = service.index_company_chunks(ticker="AAPL")
    assert summary2.total_discovered == 2
    assert summary2.newly_indexed == 0
    assert summary2.already_indexed == 2

    # 4. Modify one chunk text in SQLite
    with db.connection() as conn:
        conn.execute(
            """
            UPDATE document_chunks
            SET chunk_text = 'Updated risk factor: Cyber risks have significantly expanded.'
            WHERE chunk_index = 0 AND section_identifier = 'ITEM_1A';
            """
        )

    # 5. Third run: should detect change in ITEM_1A and update it
    summary3 = service.index_company_chunks(ticker="AAPL")
    assert summary3.total_discovered == 2
    assert summary3.newly_indexed == 0
    assert summary3.updated_indexed == 1
    assert summary3.already_indexed == 1

    # 6. Force re-index: should re-embed all
    summary4 = service.index_company_chunks(ticker="AAPL", force_reindex=True)
    assert summary4.total_discovered == 2
    assert summary4.updated_indexed == 2

    # 7. Index stats
    stats = service.get_index_stats()
    assert stats.index_size == 2
    assert stats.embedding_dimension == 384
    assert stats.active_backend == "numpy"


def test_indexing_service_failure_handling(tmp_path: Path) -> None:
    """Verify that when embedding generation fails, chunks are marked 'failed' without crashing."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)
    seed_synthetic_chunks(doc_storage)

    def failing_encoder(texts: list[str]) -> np.ndarray:
        raise RuntimeError("Simulated GPU/CPU out of memory error")

    emb_service = EmbeddingService(
        model_name="failing-model",
        dimension=384,
        encoder_fn=failing_encoder,
    )
    vector_store = NumpyVectorStore(dimension=384, index_dir=tmp_path)

    service = IndexingService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )

    summary = service.index_company_chunks(ticker="AAPL")
    assert summary.failed == 2
    assert summary.newly_indexed == 0
    assert vector_store.get_index_stats()["total_vectors"] == 0

    status = service.get_indexing_status("AAPL")
    assert status.failed_chunks == 2
    assert status.indexed_chunks == 0


def test_indexing_service_global_rebuild(tmp_path: Path) -> None:
    """Verify global rebuild_index across all companies."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)
    seed_synthetic_chunks(doc_storage)

    mock_encoder = make_deterministic_mock_encoder(dim=384)
    emb_service = EmbeddingService(
        model_name="test-model",
        dimension=384,
        encoder_fn=mock_encoder,
    )
    vector_store = NumpyVectorStore(dimension=384, index_dir=tmp_path)

    service = IndexingService(
        document_storage=doc_storage,
        embedding_service=emb_service,
        vector_store=vector_store,
    )

    # Initial index
    service.index_company_chunks(ticker="AAPL")

    # Rebuild globally (ticker=None)
    rebuild_summary = service.rebuild_index(ticker=None)
    assert rebuild_summary.total_discovered == 2
    assert rebuild_summary.newly_indexed == 2
    assert rebuild_summary.ticker is None
    assert vector_store.get_index_stats()["total_vectors"] == 2


def test_indexing_service_no_chunks_found(tmp_path: Path) -> None:
    """Verify empty summary returned when company has zero chunks in SQLite."""
    db = Database(db_path=":memory:")
    doc_storage = DocumentStorage(db=db)

    service = IndexingService(
        document_storage=doc_storage,
        embedding_service=EmbeddingService(
            dimension=384, encoder_fn=make_deterministic_mock_encoder(384)
        ),
        vector_store=NumpyVectorStore(dimension=384, index_dir=tmp_path),
    )

    res = service.index_company_chunks(ticker="EMPTY")
    assert res.total_discovered == 0
    assert res.newly_indexed == 0
    assert "No document chunks found" in res.message
