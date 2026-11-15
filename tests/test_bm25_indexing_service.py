"""Integration tests for BM25IndexingService.

Verifies incremental indexing, content hash tracking, status diagnostics,
force-reindex, company scoping, and full index rebuild.
"""

from pathlib import Path

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.retrieval.bm25_indexing_service import BM25IndexingService
from backend.retrieval.bm25_search import BM25Index
from tests.test_bm25_search import seed_test_chunks


def test_bm25_indexing_initial_and_incremental(tmp_path: Path) -> None:
    """Verify first run indexes all chunks, and second run skips unchanged chunks."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    seed_test_chunks(storage)

    bm25_idx = BM25Index(index_dir=tmp_path / "bm25")
    service = BM25IndexingService(document_storage=storage, bm25_index=bm25_idx)

    # 1. Initial indexing for AAPL
    summary1 = service.index_company_chunks(ticker="AAPL")
    assert summary1.total_discovered == 2
    assert summary1.newly_indexed == 2
    assert summary1.already_indexed == 0
    assert summary1.failed == 0
    assert bm25_idx.total_chunks == 2

    # 2. Idempotent second run - all should be skipped
    summary2 = service.index_company_chunks(ticker="AAPL")
    assert summary2.total_discovered == 2
    assert summary2.already_indexed == 2
    assert summary2.newly_indexed == 0
    assert summary2.updated_indexed == 0
    assert bm25_idx.total_chunks == 2

    # 3. Force re-index should update all chunks
    summary3 = service.index_company_chunks(ticker="AAPL", force_reindex=True)
    assert summary3.total_discovered == 2
    assert summary3.updated_indexed == 2
    assert summary3.already_indexed == 0


def test_bm25_indexing_company_scoping(tmp_path: Path) -> None:
    """Verify company-specific indexing only processes target company chunks."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    seed_test_chunks(storage)

    bm25_idx = BM25Index(index_dir=tmp_path / "bm25")
    service = BM25IndexingService(document_storage=storage, bm25_index=bm25_idx)

    # Index AAPL only
    summary_aapl = service.index_company_chunks(ticker="AAPL")
    assert summary_aapl.newly_indexed == 2
    assert bm25_idx.total_chunks == 2

    # Index MSFT only
    summary_msft = service.index_company_chunks(ticker="MSFT")
    assert summary_msft.newly_indexed == 1
    assert bm25_idx.total_chunks == 3


def test_bm25_indexing_status(tmp_path: Path) -> None:
    """Verify status diagnostics accurately report indexed, pending, and failed counts."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    seed_test_chunks(storage)

    bm25_idx = BM25Index(index_dir=tmp_path / "bm25")
    service = BM25IndexingService(document_storage=storage, bm25_index=bm25_idx)

    # Before indexing
    status_pre = service.get_indexing_status(ticker="AAPL")
    assert status_pre.total_available_chunks == 2
    assert status_pre.indexed_chunks == 0
    assert status_pre.pending_chunks == 2

    # After indexing
    service.index_company_chunks(ticker="AAPL")
    status_post = service.get_indexing_status(ticker="AAPL")
    assert status_post.total_available_chunks == 2
    assert status_post.indexed_chunks == 2
    assert status_post.pending_chunks == 0
    assert status_post.total_tokens > 0
    assert status_post.avg_doc_len > 0.0


def test_bm25_indexing_rebuild_all(tmp_path: Path) -> None:
    """Verify rebuilding all indexes wipes existing and indexes all companies."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    seed_test_chunks(storage)

    bm25_idx = BM25Index(index_dir=tmp_path / "bm25")
    service = BM25IndexingService(document_storage=storage, bm25_index=bm25_idx)

    # Rebuild all
    rebuild_summary = service.rebuild_all_indexes()
    assert rebuild_summary.total_discovered == 3  # 2 AAPL + 1 MSFT
    assert rebuild_summary.newly_indexed == 3
    assert bm25_idx.total_chunks == 3

    # Check global stats
    stats = service.get_index_stats()
    assert stats.total_chunks == 3
    assert stats.vocab_size > 0
    assert "AAPL" in stats.indexed_tickers
    assert "MSFT" in stats.indexed_tickers


def test_bm25_indexing_empty_company(tmp_path: Path) -> None:
    """Verify handling when company has no chunks."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    bm25_idx = BM25Index(index_dir=tmp_path / "bm25")
    service = BM25IndexingService(document_storage=storage, bm25_index=bm25_idx)

    res = service.index_company_chunks(ticker="UNKNOWN")
    assert res.total_discovered == 0
    assert res.newly_indexed == 0
    assert "No document chunks found" in (res.message or "")
