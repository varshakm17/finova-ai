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

        logger.info("Document and chunk tables verified in database.")

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
