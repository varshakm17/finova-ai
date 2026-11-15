"""Document and Chunk Storage Engine.

Persists ingested SEC filing documents, extracted disclosure sections,
and section-aware text chunks in SQLite with full foreign key constraints.
"""

from datetime import UTC, datetime
from typing import Any

from backend.data.chunker import DocumentChunk
from backend.data.section_extractor import ExtractedSection
from backend.data.storage import Database
from backend.utils.logger import get_logger

logger = get_logger("document_storage")


class DocumentStorage:
    """Storage manager for filing documents, sections, and chunked text."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.init_document_tables()

    def init_document_tables(self) -> None:
        """Create documents, document_sections, and document_chunks tables and indexes."""
        with self.db.connection() as conn:
            cursor = conn.cursor()

            # 1. Ingested Documents Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    cik TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    accession_number TEXT UNIQUE NOT NULL,
                    filing_type TEXT NOT NULL,
                    filing_date TEXT NOT NULL,
                    report_date TEXT,
                    primary_document TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    local_file_path TEXT NOT NULL,
                    processing_status TEXT NOT NULL,
                    document_hash TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (cik) REFERENCES companies (cik) ON DELETE CASCADE
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_docs_ticker ON documents (ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_docs_cik ON documents (cik);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_docs_accn ON documents (accession_number);"
            )

            # 2. Document Sections Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS document_sections (
                    section_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    section_identifier TEXT NOT NULL,
                    section_title TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    char_count INTEGER NOT NULL DEFAULT 0,
                    start_char INTEGER DEFAULT -1,
                    end_char INTEGER DEFAULT -1,
                    extracted_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE,
                    UNIQUE(document_id, section_identifier)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sections_doc ON document_sections (document_id);"
            )

            # 3. Document Chunks Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    filing_type TEXT NOT NULL,
                    section_identifier TEXT NOT NULL,
                    section_title TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    char_count INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE,
                    FOREIGN KEY (section_id) REFERENCES document_sections (section_id) ON DELETE CASCADE,
                    UNIQUE(document_id, section_identifier, chunk_index)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks (document_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_ticker_sec ON document_chunks (ticker, section_identifier);"
            )

            # 4. Chunk Embeddings Table (Session 05)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    embedding_id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    section_identifier TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL DEFAULT '1.0',
                    embedding_dimension INTEGER NOT NULL,
                    embedding_input_hash TEXT NOT NULL,
                    chunk_text_hash TEXT NOT NULL,
                    vector_id TEXT NOT NULL,
                    index_status TEXT NOT NULL DEFAULT 'indexed',
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (chunk_id) REFERENCES document_chunks (chunk_id) ON DELETE CASCADE,
                    UNIQUE(chunk_id, model_name)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_ticker ON chunk_embeddings (ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON chunk_embeddings (chunk_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON chunk_embeddings (vector_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_status ON chunk_embeddings (index_status);"
            )

            # 5. BM25 Sparse Index Metadata Table (Session 06)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bm25_index_metadata (
                    index_id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    section_identifier TEXT NOT NULL,
                    tokenizer_version TEXT NOT NULL DEFAULT '1.0.0',
                    content_hash TEXT NOT NULL,
                    doc_len INTEGER NOT NULL,
                    index_status TEXT NOT NULL DEFAULT 'indexed',
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (chunk_id) REFERENCES document_chunks (chunk_id) ON DELETE CASCADE,
                    UNIQUE(chunk_id, tokenizer_version)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bm25_ticker ON bm25_index_metadata (ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bm25_chunk ON bm25_index_metadata (chunk_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bm25_tok ON bm25_index_metadata (tokenizer_version);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_bm25_status ON bm25_index_metadata (index_status);"
            )

        logger.info("Document, chunk, embedding, and BM25 tables verified in database.")

    def save_document(self, doc_data: dict[str, Any]) -> str:
        """Upsert a document record in documents table.

        Args:
            doc_data: Dictionary of document attributes.

        Returns:
            str: Document ID.
        """
        doc_id = doc_data["document_id"]
        now_iso = datetime.now(UTC).isoformat()

        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, cik, ticker, company_name, accession_number,
                    filing_type, filing_date, report_date, primary_document,
                    source_url, local_file_path, processing_status, document_hash,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(accession_number) DO UPDATE SET
                    processing_status = excluded.processing_status,
                    document_hash = excluded.document_hash,
                    local_file_path = excluded.local_file_path,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at;
                """,
                (
                    doc_id,
                    doc_data["cik"],
                    doc_data["ticker"].upper(),
                    doc_data["company_name"],
                    doc_data["accession_number"],
                    doc_data["filing_type"].upper(),
                    doc_data["filing_date"],
                    doc_data.get("report_date"),
                    doc_data["primary_document"],
                    doc_data["source_url"],
                    str(doc_data["local_file_path"]),
                    doc_data["processing_status"],
                    doc_data["document_hash"],
                    doc_data.get("error_message"),
                    now_iso,
                    now_iso,
                ),
            )
        return doc_id

    def update_document_status(
        self,
        document_id: str,
        processing_status: str,
        error_message: str | None = None,
    ) -> None:
        """Update processing status and optional error message for a document."""
        now_iso = datetime.now(UTC).isoformat()
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE documents
                SET processing_status = ?, error_message = ?, updated_at = ?
                WHERE document_id = ?;
                """,
                (processing_status, error_message, now_iso, document_id),
            )

    def get_document_by_accession(self, accession_number: str) -> dict[str, Any] | None:
        """Fetch document record by SEC accession number."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE accession_number = ?;",
                (accession_number.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def list_documents_for_company(
        self,
        ticker_or_cik: str,
        filing_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List ingested documents for a company with optional filing type filter."""
        clean_target = ticker_or_cik.strip().upper()
        query = "SELECT * FROM documents WHERE (ticker = ? OR cik = ?)"
        params: list[Any] = [clean_target, clean_target]

        if filing_type:
            query += " AND filing_type = ?"
            params.append(filing_type.strip().upper())

        query += " ORDER BY filing_date DESC, created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def save_sections(self, document_id: str, sections: list[ExtractedSection]) -> int:
        """Upsert extracted sections for a document.

        Returns:
            int: Number of sections saved.
        """
        if not sections:
            return 0

        now_iso = datetime.now(UTC).isoformat()
        records = [
            (
                f"{document_id}_{s.section_identifier}",
                document_id,
                s.section_identifier,
                s.section_title,
                s.status,
                s.char_count,
                s.start_char,
                s.end_char,
                s.text,
                now_iso,
            )
            for s in sections
        ]

        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO document_sections (
                    section_id, document_id, section_identifier, section_title,
                    extraction_status, char_count, start_char, end_char,
                    extracted_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, section_identifier) DO UPDATE SET
                    section_title = excluded.section_title,
                    extraction_status = excluded.extraction_status,
                    char_count = excluded.char_count,
                    start_char = excluded.start_char,
                    end_char = excluded.end_char,
                    extracted_text = excluded.extracted_text;
                """,
                records,
            )
        return len(records)

    def get_sections_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """Retrieve all extracted sections for a document."""
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT section_id, document_id, section_identifier, section_title,
                       extraction_status, char_count, start_char, end_char, created_at
                FROM document_sections
                WHERE document_id = ?
                ORDER BY section_identifier ASC;
                """,
                (document_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> int:
        """Upsert document text chunks.

        Returns:
            int: Number of chunks saved.
        """
        if not chunks:
            return 0

        now_iso = datetime.now(UTC).isoformat()
        records = [
            (
                f"{document_id}_{c.section_identifier}_{c.chunk_index}",
                document_id,
                f"{document_id}_{c.section_identifier}",
                c.company_ticker,
                c.accession_number,
                c.filing_type,
                c.section_identifier,
                c.section_title,
                c.chunk_index,
                c.chunk_text,
                c.start_offset,
                c.end_offset,
                c.char_count,
                c.source_url,
                now_iso,
            )
            for c in chunks
        ]

        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO document_chunks (
                    chunk_id, document_id, section_id, ticker, accession_number,
                    filing_type, section_identifier, section_title, chunk_index,
                    chunk_text, start_offset, end_offset, char_count, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, section_identifier, chunk_index) DO UPDATE SET
                    chunk_text = excluded.chunk_text,
                    start_offset = excluded.start_offset,
                    end_offset = excluded.end_offset,
                    char_count = excluded.char_count,
                    source_url = excluded.source_url;
                """,
                records,
            )
        return len(records)

    def get_chunks_for_document(
        self,
        document_id: str,
        section_identifier: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Retrieve stored chunks for a document with optional section filter."""
        query = "SELECT * FROM document_chunks WHERE document_id = ?"
        params: list[Any] = [document_id]

        if section_identifier:
            query += " AND section_identifier = ?"
            params.append(section_identifier.strip().upper())

        query += " ORDER BY section_identifier ASC, chunk_index ASC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def delete_document_and_chunks(self, accession_number: str) -> bool:
        """Cascade-delete document, sections, and chunks by accession number."""
        doc = self.get_document_by_accession(accession_number)
        if not doc:
            return False

        with self.db.connection() as conn:
            conn.execute(
                "DELETE FROM documents WHERE accession_number = ?;",
                (accession_number.strip(),),
            )
        logger.info("Deleted document %s and cascading children", accession_number)
        return True

    # -------------------------------------------------------------------------
    # Chunk Retrieval & Embedding Persistence (Session 05)
    # -------------------------------------------------------------------------
    def get_chunks_for_ticker(
        self,
        ticker: str,
        filing_type: str | None = None,
        accession_number: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Retrieve stored chunks for a company with optional filing type and accession filters."""
        query = "SELECT * FROM document_chunks WHERE ticker = ?"
        params: list[Any] = [ticker.strip().upper()]

        if filing_type:
            query += " AND filing_type = ?"
            params.append(filing_type.strip().upper())

        if accession_number:
            query += " AND accession_number = ?"
            params.append(accession_number.strip())

        query += " ORDER BY accession_number DESC, section_identifier ASC, chunk_index ASC LIMIT ?;"
        params.append(limit)

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_chunk_with_provenance(self, chunk_id: str) -> dict[str, Any] | None:
        """Fetch chunk details joined with document metadata for full filing provenance."""
        query = """
            SELECT c.chunk_id, c.document_id, c.section_id, c.ticker, c.accession_number,
                   c.filing_type, c.section_identifier, c.section_title, c.chunk_index,
                   c.chunk_text, c.start_offset, c.end_offset, c.char_count, c.source_url,
                   d.company_name, d.cik, d.filing_date, d.report_date
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.document_id
            WHERE c.chunk_id = ?;
        """
        with self.db.connection() as conn:
            row = conn.execute(query, (chunk_id.strip(),)).fetchone()
            return dict(row) if row else None

    def save_chunk_embeddings(self, records: list[dict[str, Any]]) -> int:
        """Upsert chunk embedding metadata records.

        Args:
            records: List of embedding record dictionaries.

        Returns:
            int: Number of records saved.
        """
        if not records:
            return 0

        now_iso = datetime.now(UTC).isoformat()
        rows = [
            (
                r["embedding_id"],
                r["chunk_id"],
                r["document_id"],
                r["ticker"].strip().upper(),
                r["accession_number"],
                r["section_identifier"],
                r["model_name"],
                r.get("model_version", "1.0"),
                r["embedding_dimension"],
                r["embedding_input_hash"],
                r["chunk_text_hash"],
                r["vector_id"],
                r.get("index_status", "indexed"),
                r.get("error_message"),
                r.get("created_at", now_iso),
                now_iso,
            )
            for r in records
        ]

        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO chunk_embeddings (
                    embedding_id, chunk_id, document_id, ticker, accession_number,
                    section_identifier, model_name, model_version, embedding_dimension,
                    embedding_input_hash, chunk_text_hash, vector_id, index_status,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, model_name) DO UPDATE SET
                    embedding_input_hash = excluded.embedding_input_hash,
                    chunk_text_hash = excluded.chunk_text_hash,
                    vector_id = excluded.vector_id,
                    index_status = excluded.index_status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at;
                """,
                rows,
            )
        return len(rows)

    def get_chunk_embedding(
        self, chunk_id: str, model_name: str
    ) -> dict[str, Any] | None:
        """Fetch a specific chunk embedding metadata record."""
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM chunk_embeddings
                WHERE chunk_id = ? AND model_name = ?;
                """,
                (chunk_id.strip(), model_name.strip()),
            ).fetchone()
            return dict(row) if row else None

    def get_chunk_embeddings_for_ticker(
        self,
        ticker: str,
        model_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve embedding metadata records for a company."""
        query = "SELECT * FROM chunk_embeddings WHERE ticker = ?"
        params: list[Any] = [ticker.strip().upper()]

        if model_name:
            query += " AND model_name = ?"
            params.append(model_name.strip())

        query += " ORDER BY created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_embedding_counts_for_ticker(
        self,
        ticker: str,
        model_name: str,
    ) -> dict[str, int]:
        """Compute total chunks, indexed chunks, pending, and failed for a company."""
        clean_ticker = ticker.strip().upper()
        clean_model = model_name.strip()

        with self.db.connection() as conn:
            # 1. Total available chunks
            total_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM document_chunks WHERE ticker = ?;",
                (clean_ticker,),
            ).fetchone()
            total_chunks = total_row["cnt"] if total_row else 0

            # 2. Status counts from chunk_embeddings
            status_rows = conn.execute(
                """
                SELECT index_status, COUNT(*) as cnt
                FROM chunk_embeddings
                WHERE ticker = ? AND model_name = ?
                GROUP BY index_status;
                """,
                (clean_ticker, clean_model),
            ).fetchall()

            status_map = {r["index_status"]: r["cnt"] for r in status_rows}

            indexed = status_map.get("indexed", 0)
            failed = status_map.get("failed", 0)
            pending = max(0, total_chunks - indexed - failed)

            return {
                "total_available_chunks": total_chunks,
                "indexed_chunks": indexed,
                "pending_chunks": pending,
                "failed_chunks": failed,
            }

    def get_all_chunk_embeddings(
        self,
        model_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve all embedding metadata records across all companies."""
        query = "SELECT * FROM chunk_embeddings"
        params: list[Any] = []

        if model_name:
            query += " WHERE model_name = ?"
            params.append(model_name.strip())

        query += " ORDER BY created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def delete_chunk_embeddings(self, chunk_ids: list[str]) -> int:
        """Delete embedding records by chunk IDs."""
        if not chunk_ids:
            return 0

        placeholders = ",".join("?" for _ in chunk_ids)
        with self.db.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM chunk_embeddings WHERE chunk_id IN ({placeholders});",
                chunk_ids,
            )
            return cursor.rowcount

    # ---------------------------------------------------------
    # BM25 Sparse Index Metadata Methods (Session 06)
    # ---------------------------------------------------------

    def save_bm25_metadata(self, records: list[dict[str, Any]]) -> int:
        """Batch upsert BM25 index metadata records into SQLite.

        Args:
            records: List of dictionaries matching bm25_index_metadata schema.

        Returns:
            int: Number of records saved.
        """
        if not records:
            return 0

        now_iso = datetime.now(UTC).isoformat()
        rows = [
            (
                r["index_id"],
                r["chunk_id"],
                r["document_id"],
                r["ticker"].strip().upper(),
                r["accession_number"],
                r["section_identifier"],
                r.get("tokenizer_version", "1.0.0"),
                r["content_hash"],
                r.get("doc_len", 0),
                r.get("index_status", "indexed"),
                r.get("error_message"),
                r.get("created_at", now_iso),
                now_iso,
            )
            for r in records
        ]

        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO bm25_index_metadata (
                    index_id, chunk_id, document_id, ticker, accession_number,
                    section_identifier, tokenizer_version, content_hash, doc_len,
                    index_status, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id, tokenizer_version) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    doc_len = excluded.doc_len,
                    index_status = excluded.index_status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at;
                """,
                rows,
            )
        return len(rows)

    def get_bm25_metadata_for_chunk(
        self, chunk_id: str, tokenizer_version: str = "1.0.0"
    ) -> dict[str, Any] | None:
        """Fetch a specific BM25 index metadata record."""
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM bm25_index_metadata
                WHERE chunk_id = ? AND tokenizer_version = ?;
                """,
                (chunk_id.strip(), tokenizer_version.strip()),
            ).fetchone()
            return dict(row) if row else None

    def get_bm25_metadata_for_ticker(
        self,
        ticker: str,
        tokenizer_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve BM25 index metadata records for a company."""
        clean_ticker = ticker.strip().upper()
        query = "SELECT * FROM bm25_index_metadata WHERE ticker = ?"
        params: list[Any] = [clean_ticker]

        if tokenizer_version:
            query += " AND tokenizer_version = ?"
            params.append(tokenizer_version.strip())

        query += " ORDER BY created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_bm25_counts_for_ticker(
        self,
        ticker: str,
        tokenizer_version: str = "1.0.0",
    ) -> dict[str, int]:
        """Get diagnostic summary of chunk indexing counts for BM25."""
        clean_ticker = ticker.strip().upper()
        clean_tok = tokenizer_version.strip()

        with self.db.connection() as conn:
            # 1. Total chunks available
            tot_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM document_chunks WHERE ticker = ?;",
                (clean_ticker,),
            ).fetchone()
            total_chunks = tot_row["cnt"] if tot_row else 0

            # 2. Status counts from bm25_index_metadata
            status_rows = conn.execute(
                """
                SELECT index_status, COUNT(*) as cnt
                FROM bm25_index_metadata
                WHERE ticker = ? AND tokenizer_version = ?
                GROUP BY index_status;
                """,
                (clean_ticker, clean_tok),
            ).fetchall()

            status_map = {r["index_status"]: r["cnt"] for r in status_rows}

            indexed = status_map.get("indexed", 0)
            failed = status_map.get("failed", 0)
            pending = max(0, total_chunks - indexed - failed)

            return {
                "total_available_chunks": total_chunks,
                "indexed_chunks": indexed,
                "pending_chunks": pending,
                "failed_chunks": failed,
            }

    def get_all_bm25_metadata(
        self,
        tokenizer_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve all BM25 index metadata records across all companies."""
        query = "SELECT * FROM bm25_index_metadata"
        params: list[Any] = []

        if tokenizer_version:
            query += " WHERE tokenizer_version = ?"
            params.append(tokenizer_version.strip())

        query += " ORDER BY created_at DESC;"

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def delete_bm25_metadata(self, chunk_ids: list[str]) -> int:
        """Delete BM25 metadata records by chunk IDs."""
        if not chunk_ids:
            return 0

        placeholders = ",".join("?" for _ in chunk_ids)
        with self.db.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM bm25_index_metadata WHERE chunk_id IN ({placeholders});",
                chunk_ids,
            )
            return cursor.rowcount

    def delete_bm25_metadata_for_ticker(self, ticker: str) -> int:
        """Delete all BM25 metadata records for a given company ticker."""
        clean_ticker = ticker.strip().upper()
        with self.db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM bm25_index_metadata WHERE ticker = ?;",
                (clean_ticker,),
            )
            return cursor.rowcount
