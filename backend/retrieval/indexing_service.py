"""Document Chunk Embedding and Vector Indexing Pipeline.

Discovers unindexed or modified statutory SEC filing chunks in SQLite,
prepares contextualized text representations, generates dense vector embeddings,
persists vectors into the persistent vector store, and tracks provenance metadata.
"""

import re
import time
from datetime import UTC, datetime

from backend.data.document_storage import DocumentStorage
from backend.retrieval.embedding_service import EmbeddingService
from backend.retrieval.retrieval_models import (
    EmbeddingStatusResponse,
    IndexingSummary,
    IndexStatsResponse,
)
from backend.retrieval.text_preprocessor import TextPreprocessor
from backend.retrieval.vector_store import BaseVectorStore, get_vector_store
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("indexing_service")


class IndexingService:
    """Orchestrates incremental, idempotent document chunk indexing and vector storage."""

    def __init__(
        self,
        document_storage: DocumentStorage | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store: BaseVectorStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.embedding_service = embedding_service or EmbeddingService(
            settings=self.settings
        )
        self.vector_store = vector_store or get_vector_store(
            backend=self.settings.EMBEDDING_BACKEND,
            dimension=self.embedding_service.get_embedding_dimension(),
            index_dir=self.settings.EMBEDDING_INDEX_DIR,
        )

    def _sanitize_model_tag(self, model_name: str) -> str:
        """Create a filesystem and SQL-safe short model identifier."""
        return re.sub(r"[^a-zA-Z0-9_]+", "_", model_name)

    def index_company_chunks(
        self,
        ticker: str,
        filing_type: str | None = None,
        accession_number: str | None = None,
        force_reindex: bool = False,
        batch_size: int | None = None,
    ) -> IndexingSummary:
        """Incrementally index eligible document chunks for a company into the vector store.

        Detects unindexed chunks as well as chunks whose content has changed,
        generates normalized embeddings in batches, updates SQLite metadata,
        and synchronizes vector store persistence.

        Args:
            ticker: Company stock ticker symbol.
            filing_type: Optional filing type filter (e.g. '10-K', '10-Q').
            accession_number: Optional specific filing accession number filter.
            force_reindex: If True, forces re-embedding even if content hashes match.
            batch_size: Batch size override for embedding model inference.

        Returns:
            IndexingSummary: Detailed breakdown of the indexing run.
        """
        start_time = time.perf_counter()
        clean_ticker = ticker.strip().upper()
        active_model = self.embedding_service.model_name
        model_tag = self._sanitize_model_tag(active_model)
        dim = self.embedding_service.get_embedding_dimension()

        # 1. Retrieve candidate chunks from SQLite
        all_chunks = self.doc_storage.get_chunks_for_ticker(
            ticker=clean_ticker,
            filing_type=filing_type,
            accession_number=accession_number,
        )
        total_discovered = len(all_chunks)

        if total_discovered == 0:
            duration = time.perf_counter() - start_time
            return IndexingSummary(
                ticker=clean_ticker,
                total_discovered=0,
                already_indexed=0,
                newly_indexed=0,
                updated_indexed=0,
                failed=0,
                model_name=active_model,
                backend=self.vector_store.backend_name,
                embedding_dimension=dim,
                duration_seconds=round(duration, 4),
                message=f"No document chunks found for ticker '{clean_ticker}' matching criteria.",
            )

        # 2. Identify chunks requiring embedding generation
        to_index_chunks: list[
            tuple[dict, str, str, str]
        ] = []  # (chunk, prepared_text, raw_hash, input_hash)
        already_indexed = 0
        updated_count = 0
        new_count = 0

        for chunk in all_chunks:
            chunk_id = chunk["chunk_id"]
            raw_text = chunk["chunk_text"]

            prepared_text = TextPreprocessor.prepare_chunk_text(
                chunk_text=raw_text,
                ticker=chunk["ticker"],
                filing_type=chunk["filing_type"],
                section_title=chunk["section_title"],
                include_context=True,
            )
            raw_hash = TextPreprocessor.compute_text_hash(raw_text)
            input_hash = TextPreprocessor.compute_text_hash(prepared_text)

            existing = self.doc_storage.get_chunk_embedding(chunk_id, active_model)

            if not existing:
                to_index_chunks.append((chunk, prepared_text, raw_hash, input_hash))
                new_count += 1
            elif force_reindex or (
                existing.get("chunk_text_hash") != raw_hash
                or existing.get("embedding_input_hash") != input_hash
            ):
                to_index_chunks.append((chunk, prepared_text, raw_hash, input_hash))
                updated_count += 1
            elif existing.get("index_status") != "indexed":
                to_index_chunks.append((chunk, prepared_text, raw_hash, input_hash))
                new_count += 1
            else:
                already_indexed += 1

        if not to_index_chunks:
            duration = time.perf_counter() - start_time
            return IndexingSummary(
                ticker=clean_ticker,
                total_discovered=total_discovered,
                already_indexed=already_indexed,
                newly_indexed=0,
                updated_indexed=0,
                failed=0,
                model_name=active_model,
                backend=self.vector_store.backend_name,
                embedding_dimension=dim,
                duration_seconds=round(duration, 4),
                message="All chunks are already up-to-date in the vector index.",
            )

        # 3. Batch processing of chunks requiring embeddings
        eff_batch = batch_size or self.embedding_service.batch_size
        newly_indexed_actual = 0
        updated_indexed_actual = 0
        failed_count = 0

        for i in range(0, len(to_index_chunks), eff_batch):
            batch = to_index_chunks[i : i + eff_batch]
            batch_texts = [item[1] for item in batch]
            batch_chunks = [item[0] for item in batch]

            try:
                # Generate embeddings for the batch
                embeddings = self.embedding_service.encode_texts(batch_texts)

                # Add vectors to persistent store
                vector_ids = [c["chunk_id"] for c in batch_chunks]
                self.vector_store.add_vectors(vector_ids, embeddings)

                # Prepare database records
                records_to_save: list[dict] = []
                now_iso = datetime.now(UTC).isoformat()

                for chunk, _prep, raw_h, in_h in batch:
                    c_id = chunk["chunk_id"]
                    is_update = (
                        self.doc_storage.get_chunk_embedding(c_id, active_model)
                        is not None
                    )

                    rec = {
                        "embedding_id": f"{c_id}_{model_tag}",
                        "chunk_id": c_id,
                        "document_id": chunk["document_id"],
                        "ticker": chunk["ticker"],
                        "accession_number": chunk["accession_number"],
                        "section_identifier": chunk["section_identifier"],
                        "model_name": active_model,
                        "model_version": "1.0",
                        "embedding_dimension": dim,
                        "embedding_input_hash": in_h,
                        "chunk_text_hash": raw_h,
                        "vector_id": c_id,
                        "index_status": "indexed",
                        "error_message": None,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    records_to_save.append(rec)

                    if is_update:
                        updated_indexed_actual += 1
                    else:
                        newly_indexed_actual += 1

                # Persist metadata records in SQLite
                self.doc_storage.save_chunk_embeddings(records_to_save)

            except Exception as exc:  # noqa: BLE001
                logger.error("Error embedding batch of %d chunks: %s", len(batch), exc)
                failed_count += len(batch)

                # Record failure in SQLite without adding vectors
                now_iso = datetime.now(UTC).isoformat()
                failure_records: list[dict] = []
                for chunk, _prep, raw_h, in_h in batch:
                    c_id = chunk["chunk_id"]
                    failure_records.append(
                        {
                            "embedding_id": f"{c_id}_{model_tag}",
                            "chunk_id": c_id,
                            "document_id": chunk["document_id"],
                            "ticker": chunk["ticker"],
                            "accession_number": chunk["accession_number"],
                            "section_identifier": chunk["section_identifier"],
                            "model_name": active_model,
                            "model_version": "1.0",
                            "embedding_dimension": dim,
                            "embedding_input_hash": in_h,
                            "chunk_text_hash": raw_h,
                            "vector_id": c_id,
                            "index_status": "failed",
                            "error_message": str(exc),
                            "created_at": now_iso,
                            "updated_at": now_iso,
                        }
                    )
                self.doc_storage.save_chunk_embeddings(failure_records)

        # 4. Persist vector store to disk
        self.vector_store.save()

        duration = time.perf_counter() - start_time
        return IndexingSummary(
            ticker=clean_ticker,
            total_discovered=total_discovered,
            already_indexed=already_indexed,
            newly_indexed=newly_indexed_actual,
            updated_indexed=updated_indexed_actual,
            failed=failed_count,
            model_name=active_model,
            backend=self.vector_store.backend_name,
            embedding_dimension=dim,
            duration_seconds=round(duration, 4),
            message=(
                f"Completed indexing for '{clean_ticker}'. "
                f"Newly indexed: {newly_indexed_actual}, Updated: {updated_indexed_actual}, "
                f"Skipped: {already_indexed}, Failed: {failed_count}."
            ),
        )

    def rebuild_index(self, ticker: str | None = None) -> IndexingSummary:
        """Rebuild the vector index from SQLite chunks.

        If ticker is provided, re-indexes chunks for that company.
        If ticker is None, clears the vector store and re-indexes all stored chunks.

        Args:
            ticker: Optional target company ticker.

        Returns:
            IndexingSummary: Summary of rebuild execution.
        """
        logger.info("Initiating vector index rebuild (ticker=%s)...", ticker)
        if ticker:
            return self.index_company_chunks(ticker=ticker, force_reindex=True)

        # Full index rebuild
        self.vector_store.clear()
        all_embeddings = self.doc_storage.get_all_chunk_embeddings(
            model_name=self.embedding_service.model_name
        )
        unique_tickers = sorted({r["ticker"] for r in all_embeddings})

        total_discovered = 0
        total_newly_indexed = 0
        total_failed = 0

        start_time = time.perf_counter()
        for t in unique_tickers:
            res = self.index_company_chunks(ticker=t, force_reindex=True)
            total_discovered += res.total_discovered
            total_newly_indexed += res.newly_indexed + res.updated_indexed
            total_failed += res.failed

        duration = time.perf_counter() - start_time
        return IndexingSummary(
            ticker=None,
            total_discovered=total_discovered,
            already_indexed=0,
            newly_indexed=total_newly_indexed,
            updated_indexed=0,
            failed=total_failed,
            model_name=self.embedding_service.model_name,
            backend=self.vector_store.backend_name,
            embedding_dimension=self.embedding_service.get_embedding_dimension(),
            duration_seconds=round(duration, 4),
            message=f"Global index rebuild completed across {len(unique_tickers)} companies.",
        )

    def get_indexing_status(self, ticker: str) -> EmbeddingStatusResponse:
        """Fetch indexing status counts and configuration diagnostics for a company."""
        clean_ticker = ticker.strip().upper()
        counts = self.doc_storage.get_embedding_counts_for_ticker(
            ticker=clean_ticker,
            model_name=self.embedding_service.model_name,
        )
        return EmbeddingStatusResponse(
            ticker=clean_ticker,
            total_available_chunks=counts["total_available_chunks"],
            indexed_chunks=counts["indexed_chunks"],
            pending_chunks=counts["pending_chunks"],
            failed_chunks=counts["failed_chunks"],
            active_model=self.embedding_service.model_name,
            active_vector_backend=self.vector_store.backend_name,
            embedding_dimension=self.embedding_service.get_embedding_dimension(),
        )

    def get_index_stats(self) -> IndexStatsResponse:
        """Retrieve vector index size, storage location, and backend statistics."""
        stats = self.vector_store.get_index_stats()
        all_records = self.doc_storage.get_all_chunk_embeddings(
            model_name=self.embedding_service.model_name
        )
        total_indexed_db = sum(
            1 for r in all_records if r.get("index_status") == "indexed"
        )

        return IndexStatsResponse(
            active_backend=stats["backend"],
            index_size=stats["total_vectors"],
            embedding_dimension=stats["dimension"],
            model_name=self.embedding_service.model_name,
            index_location="storage://datasets/indexes",
            last_updated_at=datetime.now(UTC).isoformat(),
            total_indexed_chunks=total_indexed_db,
        )
