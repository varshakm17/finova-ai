"""Filing Ingestion Service.

Coordinates end-to-end filing ingestion: downloading, parsing,
section extraction, boundary-aware chunking, and relational persistence.
"""

from dataclasses import dataclass, field

from backend.data.chunker import DocumentChunk, SectionChunker
from backend.data.company_service import CompanyService, normalize_ticker
from backend.data.document_storage import DocumentStorage
from backend.data.filing_downloader import DownloadedFiling, FilingDownloader
from backend.data.html_parser import HTMLDocumentParser
from backend.data.sec_client import SECClient
from backend.data.section_extractor import ExtractedSection, SectionExtractor
from backend.data.storage import Database
from backend.utils.logger import get_logger

logger = get_logger("filing_ingestion_service")


@dataclass
class IngestionResult:
    """Structured summary returned upon completing filing ingestion."""

    document_id: str
    ticker: str
    cik: str
    company_name: str
    accession_number: str
    filing_type: str
    filing_date: str
    report_date: str | None
    processing_status: (
        str  # 'completed', 'already_ingested', 'partially_processed', 'failed'
    )
    sections_extracted: list[str] = field(default_factory=list)
    sections_not_found: list[str] = field(default_factory=list)
    total_chunks: int = 0
    document_hash: str = ""
    file_size_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class FilingIngestionService:
    """Orchestrates end-to-end ingestion of statutory SEC filings."""

    def __init__(
        self,
        company_service: CompanyService | None = None,
        sec_client: SECClient | None = None,
        downloader: FilingDownloader | None = None,
        html_parser: HTMLDocumentParser | None = None,
        section_extractor: SectionExtractor | None = None,
        chunker: SectionChunker | None = None,
        document_storage: DocumentStorage | None = None,
        db: Database | None = None,
    ) -> None:
        self.db = db or Database()
        self.sec_client = sec_client or SECClient()
        self.company_service = company_service or CompanyService(
            sec_client=self.sec_client
        )
        self.downloader = downloader or FilingDownloader()
        self.html_parser = html_parser or HTMLDocumentParser()
        self.section_extractor = section_extractor or SectionExtractor()
        self.chunker = chunker or SectionChunker()
        self.doc_storage = document_storage or DocumentStorage(db=self.db)

    def ingest_filing(
        self,
        ticker: str,
        accession_number: str,
        force_refresh: bool = False,
    ) -> IngestionResult:
        """Ingest a specific SEC filing by ticker and accession number.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL').
            accession_number: SEC accession number (e.g., '0000320193-23-000106').
            force_refresh: If True, re-download and re-chunk even if already ingested.

        Returns:
            IngestionResult: Structured summary of ingestion outcome.
        """
        clean_ticker = normalize_ticker(ticker)
        clean_accn = accession_number.strip()

        # 1. Resolve Company Identity
        identity = self.company_service.get_company_by_ticker(clean_ticker)
        if not identity:
            return IngestionResult(
                document_id="",
                ticker=clean_ticker,
                cik="",
                company_name="",
                accession_number=clean_accn,
                filing_type="",
                filing_date="",
                report_date=None,
                processing_status="failed",
                error=f"Company with ticker '{clean_ticker}' not found in SEC directory.",
            )

        cik = identity["cik"]
        company_name = identity["name"]
        doc_id = f"{cik}_{clean_accn.replace('-', '')}"

        # Guarantee company exists in SQLite companies table to satisfy foreign keys
        self.db.save_company({"cik": cik, "ticker": clean_ticker, "name": company_name})

        # 2. Check if already ingested
        existing_doc = self.doc_storage.get_document_by_accession(clean_accn)
        if (
            existing_doc
            and existing_doc.get("processing_status") == "completed"
            and not force_refresh
        ):
            sections = self.doc_storage.get_sections_for_document(doc_id)
            chunks = self.doc_storage.get_chunks_for_document(doc_id)
            extracted_sec_ids = [
                s["section_identifier"]
                for s in sections
                if s["extraction_status"] == "extracted"
            ]
            not_found_sec_ids = [
                s["section_identifier"]
                for s in sections
                if s["extraction_status"] != "extracted"
            ]

            logger.info("Filing %s already ingested for %s", clean_accn, clean_ticker)
            return IngestionResult(
                document_id=doc_id,
                ticker=clean_ticker,
                cik=cik,
                company_name=company_name,
                accession_number=clean_accn,
                filing_type=existing_doc["filing_type"],
                filing_date=existing_doc["filing_date"],
                report_date=existing_doc.get("report_date"),
                processing_status="already_ingested",
                sections_extracted=extracted_sec_ids,
                sections_not_found=not_found_sec_ids,
                total_chunks=len(chunks),
                document_hash=existing_doc["document_hash"],
                file_size_bytes=0,
                warnings=[
                    "Document was previously ingested. Use force_refresh=True to reprocess."
                ],
            )

        # 3. Retrieve Filing Metadata
        filings = self.sec_client.get_company_filings(cik)
        target_filing = next(
            (f for f in filings if f["accession_number"] == clean_accn), None
        )

        if not target_filing:
            return IngestionResult(
                document_id=doc_id,
                ticker=clean_ticker,
                cik=cik,
                company_name=company_name,
                accession_number=clean_accn,
                filing_type="",
                filing_date="",
                report_date=None,
                processing_status="failed",
                error=f"Filing with accession number '{clean_accn}' not found for {clean_ticker}.",
            )

        form = target_filing["form"]
        filing_date = target_filing["filing_date"]
        report_date = target_filing.get("report_date")
        primary_doc = target_filing["primary_document"]
        source_url = target_filing["url"]

        if not source_url or not primary_doc:
            return IngestionResult(
                document_id=doc_id,
                ticker=clean_ticker,
                cik=cik,
                company_name=company_name,
                accession_number=clean_accn,
                filing_type=form,
                filing_date=filing_date,
                report_date=report_date,
                processing_status="failed",
                error="Filing record does not declare a valid primary HTML document or archive URL.",
            )

        # 4. If force refresh, clear old records first
        if force_refresh and existing_doc:
            self.doc_storage.delete_document_and_chunks(clean_accn)

        # 5. Download Primary Filing Document
        try:
            downloaded: DownloadedFiling = self.downloader.download_filing(
                cik=cik,
                ticker=clean_ticker,
                accession_number=clean_accn,
                form=form,
                primary_document=primary_doc,
                source_url=source_url,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Download failed for filing %s: %s", clean_accn, exc)
            self.doc_storage.save_document(
                {
                    "document_id": doc_id,
                    "cik": cik,
                    "ticker": clean_ticker,
                    "company_name": company_name,
                    "accession_number": clean_accn,
                    "filing_type": form,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "primary_document": primary_doc,
                    "source_url": source_url,
                    "local_file_path": "",
                    "processing_status": "failed",
                    "document_hash": "",
                    "error_message": f"Download error: {exc}",
                }
            )
            return IngestionResult(
                document_id=doc_id,
                ticker=clean_ticker,
                cik=cik,
                company_name=company_name,
                accession_number=clean_accn,
                filing_type=form,
                filing_date=filing_date,
                report_date=report_date,
                processing_status="failed",
                error=f"Download failed: {exc}",
            )

        # Persist downloaded status in database
        self.doc_storage.save_document(
            {
                "document_id": doc_id,
                "cik": cik,
                "ticker": clean_ticker,
                "company_name": company_name,
                "accession_number": clean_accn,
                "filing_type": form,
                "filing_date": filing_date,
                "report_date": report_date,
                "primary_document": primary_doc,
                "source_url": source_url,
                "local_file_path": str(downloaded.local_file_path),
                "processing_status": "downloaded",
                "document_hash": downloaded.document_hash,
                "error_message": None,
            }
        )

        # 6. Parse HTML
        try:
            raw_html = downloaded.local_file_path.read_text(
                encoding="utf-8", errors="replace"
            )
            parsed_text = self.html_parser.parse_html(raw_html)
            self.doc_storage.update_document_status(doc_id, "parsed")
        except Exception as exc:  # noqa: BLE001
            logger.error("HTML parsing failed for filing %s: %s", clean_accn, exc)
            self.doc_storage.update_document_status(
                doc_id, "failed", f"Parsing error: {exc}"
            )
            return IngestionResult(
                document_id=doc_id,
                ticker=clean_ticker,
                cik=cik,
                company_name=company_name,
                accession_number=clean_accn,
                filing_type=form,
                filing_date=filing_date,
                report_date=report_date,
                processing_status="failed",
                document_hash=downloaded.document_hash,
                file_size_bytes=downloaded.file_size_bytes,
                error=f"HTML parsing failed: {exc}",
            )

        # 7. Extract Sections
        sections: list[ExtractedSection] = self.section_extractor.extract_sections(
            text=parsed_text, form_type=form
        )
        self.doc_storage.save_sections(doc_id, sections)

        extracted_ids: list[str] = []
        not_found_ids: list[str] = []
        warnings: list[str] = []

        all_chunks: list[DocumentChunk] = []

        # 8. Generate Section-Aware Chunks
        for sec in sections:
            if sec.status == "extracted" and sec.text:
                extracted_ids.append(sec.section_identifier)
                sec_chunks = self.chunker.chunk_section(
                    section_text=sec.text,
                    company_ticker=clean_ticker,
                    company_cik=cik,
                    company_name=company_name,
                    accession_number=clean_accn,
                    filing_type=form,
                    filing_date=filing_date,
                    report_date=report_date or "",
                    section_identifier=sec.section_identifier,
                    section_title=sec.section_title,
                    source_url=source_url,
                    base_offset=max(sec.start_char, 0),
                )
                all_chunks.extend(sec_chunks)
            else:
                not_found_ids.append(sec.section_identifier)
                warnings.append(
                    f"Section '{sec.section_identifier}' ({sec.section_title}) could not be extracted (status: {sec.status})."
                )

        # 9. Persist Chunks
        self.doc_storage.save_chunks(doc_id, all_chunks)

        final_status = "completed" if extracted_ids else "partially_processed"
        self.doc_storage.update_document_status(doc_id, final_status)

        logger.info(
            "Filing %s ingestion complete: %d sections extracted, %d chunks saved",
            clean_accn,
            len(extracted_ids),
            len(all_chunks),
        )

        return IngestionResult(
            document_id=doc_id,
            ticker=clean_ticker,
            cik=cik,
            company_name=company_name,
            accession_number=clean_accn,
            filing_type=form,
            filing_date=filing_date,
            report_date=report_date,
            processing_status=final_status,
            sections_extracted=extracted_ids,
            sections_not_found=not_found_ids,
            total_chunks=len(all_chunks),
            document_hash=downloaded.document_hash,
            file_size_bytes=downloaded.file_size_bytes,
            warnings=warnings,
        )
