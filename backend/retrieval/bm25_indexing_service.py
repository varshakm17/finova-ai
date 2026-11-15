"""Incremental BM25 Indexing Service for Corporate SEC Filings.

Coordinates deterministic tokenization, content-hash differential tracking,
safe JSON persistence, and SQLite metadata synchronization for sparse retrieval.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from backend.data.document_storage import DocumentStorage
from backend.retrieval.bm25_search import BM25Index, FinancialTokenizer
from backend.retrieval.retrieval_models import (
    BM25IndexingSummary,
    BM25IndexStatsResponse,
    BM25IndexStatusResponse,
)
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("bm25_indexing_service")


class BM25IndexingService:
    """Orchestrates incremental BM25 indexing and state persistence."""

    def __init__(
        self,
        document_storage: DocumentStorage | None = None,
        bm25_index: BM25Index | None = None,
        tokenizer: FinancialTokenizer | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.tokenizer = tokenizer or FinancialTokenizer(
            version=self.settings.BM25_TOKENIZER_VERSION
        )
        self.bm25_index = bm25_index or BM25Index(
            index_dir=self.settings.BM25_INDEX_DIR,
            tokenizer=self.tokenizer,
            k1=self.settings.BM25_K1,
            b=self.settings.BM25_B,
        )

    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Compute SHA-256 hash of chunk text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def index_company_chunks(
        self,
        ticker: str,
        filing_type: str | None = None,
        accession_number: str | None = None,
        force_reindex: bool = False,
    ) -> BM25IndexingSummary:
        """Perform incremental BM25 indexing for a company's document chunks.

        Args:
            ticker: Normalized company ticker symbol (e.g. 'AAPL').
            filing_type: Optional filing type filter (e.g. '10-K', '10-Q').
            accession_number: Optional specific accession number filter.
            force_reindex: If True, re-indexes chunks even if content hash matches.

        Returns:
            BM25IndexingSummary: Summary of chunks discovered, indexed, and skipped.
        """
        start_time = time.perf_counter()
        clean_ticker = ticker.strip().upper()

        # 1. Discover stored chunks for company
        discovered_chunks = self.doc_storage.get_chunks_for_ticker(
            ticker=clean_ticker,
            filing_type=filing_type,
            accession_number=accession_number,
        )

        total_discovered = len(discovered_chunks)
        if total_discovered == 0:
            elapsed = time.perf_counter() - start_time
            return BM25IndexingSummary(
                ticker=clean_ticker,
                total_discovered=0,
                already_indexed=0,
                newly_indexed=0,
                updated_indexed=0,
                removed=0,
                failed=0,
                tokenizer_version=self.tokenizer.version,
                duration_seconds=round(elapsed, 4),
                message=f"No document chunks found in storage for ticker {clean_ticker}.",
            )

        already_indexed = 0
        newly_indexed = 0
        updated_indexed = 0
        failed = 0
        index_modified = False

        records_to_save: list[dict[str, Any]] = []

        # 2. Process each chunk
        for chunk in discovered_chunks:
            c_id = chunk["chunk_id"]
            text = chunk["chunk_text"]
            content_hash = self.compute_content_hash(text)

            existing_meta = self.doc_storage.get_bm25_metadata_for_chunk(
                chunk_id=c_id,
                tokenizer_version=self.tokenizer.version,
            )

            is_in_index = c_id in self.bm25_index._id_to_idx

            if (
                not force_reindex
                and existing_meta
                and existing_meta.get("content_hash") == content_hash
                and existing_meta.get("index_status") == "indexed"
                and is_in_index
            ):
                already_indexed += 1
                continue

            try:
                tokens = self.bm25_index.add_or_update_chunk(
                    chunk_id=c_id,
                    text=text,
                    content_hash=content_hash,
                )
                index_modified = True

                if existing_meta:
                    updated_indexed += 1
                else:
                    newly_indexed += 1

                records_to_save.append(
                    {
                        "index_id": f"{c_id}_{self.tokenizer.version}",
                        "chunk_id": c_id,
                        "document_id": chunk["document_id"],
                        "ticker": clean_ticker,
                        "accession_number": chunk["accession_number"],
                        "section_identifier": chunk["section_identifier"],
                        "tokenizer_version": self.tokenizer.version,
                        "content_hash": content_hash,
                        "doc_len": len(tokens),
                        "index_status": "indexed",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to tokenize chunk %s: %s", c_id, exc)
                failed += 1
                records_to_save.append(
                    {
                        "index_id": f"{c_id}_{self.tokenizer.version}",
                        "chunk_id": c_id,
                        "document_id": chunk["document_id"],
                        "ticker": clean_ticker,
                        "accession_number": chunk["accession_number"],
                        "section_identifier": chunk["section_identifier"],
                        "tokenizer_version": self.tokenizer.version,
                        "content_hash": content_hash,
                        "doc_len": 0,
                        "index_status": "failed",
                        "error_message": str(exc),
                    }
                )

        # 3. If index was modified, rebuild runtime BM25 model and persist to disk
        if index_modified:
            self.bm25_index.rebuild_bm25_model()
            self.bm25_index.save()

        # 4. Save metadata in SQLite
        if records_to_save:
            self.doc_storage.save_bm25_metadata(records_to_save)

        elapsed = time.perf_counter() - start_time
        msg = (
            f"BM25 indexing complete for {clean_ticker}: "
            f"{newly_indexed} new, {updated_indexed} updated, {already_indexed} skipped, {failed} failed."
        )
        logger.info(msg)

        return BM25IndexingSummary(
            ticker=clean_ticker,
            total_discovered=total_discovered,
            already_indexed=already_indexed,
            newly_indexed=newly_indexed,
            updated_indexed=updated_indexed,
            removed=0,
            failed=failed,
            tokenizer_version=self.tokenizer.version,
            duration_seconds=round(elapsed, 4),
            message=msg,
        )

    def get_indexing_status(self, ticker: str) -> BM25IndexStatusResponse:
        """Retrieve diagnostic counts and metadata for BM25 indexing coverage."""
        clean_ticker = ticker.strip().upper()
        counts = self.doc_storage.get_bm25_counts_for_ticker(
            ticker=clean_ticker,
            tokenizer_version=self.tokenizer.version,
        )

        # Calculate tokens and avg length for this company from metadata
        meta_records = self.doc_storage.get_bm25_metadata_for_ticker(
            ticker=clean_ticker,
            tokenizer_version=self.tokenizer.version,
        )
        total_tokens = sum(
            r.get("doc_len", 0)
            for r in meta_records
            if r.get("index_status") == "indexed"
        )
        indexed_count = counts["indexed_chunks"]
        avgdl = total_tokens / max(1, indexed_count)

        last_indexed_at = meta_records[0].get("updated_at") if meta_records else None

        return BM25IndexStatusResponse(
            ticker=clean_ticker,
            total_available_chunks=counts["total_available_chunks"],
            indexed_chunks=indexed_count,
            pending_chunks=counts["pending_chunks"],
            failed_chunks=counts["failed_chunks"],
            tokenizer_version=self.tokenizer.version,
            total_tokens=total_tokens,
            avg_doc_len=round(avgdl, 2),
            last_indexed_at=last_indexed_at,
        )

    def rebuild_all_indexes(self) -> BM25IndexingSummary:
        """Wipe existing BM25 index and rebuild from all stored chunks in database.

        Returns:
            BM25IndexingSummary: Summary of rebuild execution.
        """
        start_time = time.perf_counter()
        logger.info("Starting complete BM25 index rebuild...")

        self.bm25_index.clear()

        # Find all tickers with chunks
        with self.doc_storage.db.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ticker FROM document_chunks ORDER BY ticker;"
            ).fetchall()
            tickers = [r["ticker"] for r in rows]

        total_discovered = 0
        total_newly_indexed = 0
        total_failed = 0

        for t in tickers:
            summary = self.index_company_chunks(ticker=t, force_reindex=True)
            total_discovered += summary.total_discovered
            total_newly_indexed += summary.newly_indexed
            total_failed += summary.failed

        elapsed = time.perf_counter() - start_time
        msg = f"Rebuilt BM25 index across {len(tickers)} companies: {total_newly_indexed} chunks indexed."

        return BM25IndexingSummary(
            ticker=None,
            total_discovered=total_discovered,
            already_indexed=0,
            newly_indexed=total_newly_indexed,
            updated_indexed=0,
            removed=0,
            failed=total_failed,
            tokenizer_version=self.tokenizer.version,
            duration_seconds=round(elapsed, 4),
            message=msg,
        )

    def get_index_stats(self) -> BM25IndexStatsResponse:
        """Return global index metrics across all companies."""
        stats = self.bm25_index.get_stats()

        # Find all tickers present in SQLite BM25 metadata
        all_meta = self.doc_storage.get_all_bm25_metadata(
            tokenizer_version=self.tokenizer.version
        )
        unique_tickers = sorted(
            {r["ticker"] for r in all_meta if r.get("index_status") == "indexed"}
        )

        # Get safe relative index path
        try:
            rel_path = str(self.bm25_index.index_dir.relative_to(Path.cwd()))
        except ValueError:
            rel_path = self.bm25_index.index_dir.name

        return BM25IndexStatsResponse(
            total_chunks=stats["total_chunks"],
            tokenizer_version=self.tokenizer.version,
            vocab_size=stats["vocab_size"],
            avg_doc_len=stats["avg_doc_len"],
            index_location=rel_path,
            last_updated_at=stats["last_updated_at"],
            indexed_tickers=unique_tickers,
        )
