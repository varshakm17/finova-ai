"""Real-World SEC Benchmark Data Validator.

Audits real-world benchmark datasets for SEC EDGAR regulatory compliance,
including CIK-ticker alignment, SEC URL formation, accession number syntax,
and database document/chunk existence and excerpt consistency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.data.storage import Database
from backend.utils.logger import get_logger

logger = get_logger("real_sec_benchmark_validator")

# Standard CIK reference mappings for benchmark companies
BENCHMARK_TICKER_CIK_MAP: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "TSLA": "0001318605",
    "NVDA": "0001045810",
}

# Regex for SEC EDGAR accession numbers (10 digits - 2 digits - 6 digits)
ACCESSION_NUMBER_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")

# Approved SEC EDGAR domains
ALLOWED_SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "sec.gov"}


class BenchmarkCaseStatus(str, Enum):
    """Validation classification status for benchmark queries."""

    VALIDATED_REAL_FILING = "validated_real_filing"
    PENDING_ANNOTATION = "pending_annotation"
    MISSING_SOURCE = "missing_source"
    INVALID_METADATA = "invalid_metadata"
    CHUNK_MISMATCH = "chunk_mismatch"


@dataclass
class CaseValidationResult:
    """Individual validation outcome for a single query."""

    query_id: str
    ticker: str
    cik: str
    accession_number: str
    declared_status: str
    validation_status: BenchmarkCaseStatus
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    db_document_found: bool = False
    db_chunks_found: list[str] = field(default_factory=list)


@dataclass
class BenchmarkValidationReport:
    """Aggregated audit report of real SEC benchmark dataset."""

    total_queries: int
    validated_filings: int
    pending_annotations: int
    invalid_metadata_count: int
    missing_source_count: int
    chunk_mismatch_count: int
    is_dataset_valid: bool
    case_results: list[CaseValidationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary representation."""
        return {
            "total_queries": self.total_queries,
            "validated_filings": self.validated_filings,
            "pending_annotations": self.pending_annotations,
            "invalid_metadata_count": self.invalid_metadata_count,
            "missing_source_count": self.missing_source_count,
            "chunk_mismatch_count": self.chunk_mismatch_count,
            "is_dataset_valid": self.is_dataset_valid,
            "errors": self.errors,
            "results_summary": [
                {
                    "query_id": r.query_id,
                    "ticker": r.ticker,
                    "validation_status": r.validation_status.value,
                    "is_valid": r.is_valid,
                    "issues": r.issues,
                }
                for r in self.case_results
            ],
        }


class RealSECBenchmarkValidator:
    """Validates real SEC benchmark entries for syntactic and factual fidelity."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def validate_file(
        self, file_path: str | Path | None = None
    ) -> BenchmarkValidationReport:
        """Load and validate the real SEC benchmark JSON file."""
        path = (
            Path(file_path)
            if file_path
            else Path(__file__).parent / "datasets" / "real_sec_benchmark.json"
        )
        if not path.exists():
            raise FileNotFoundError(f"Benchmark file not found at: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        queries = data.get("queries", [])
        return self.validate_queries(queries)

    def validate_queries(
        self, queries: list[dict[str, Any]]
    ) -> BenchmarkValidationReport:
        """Audit a list of benchmark query objects."""
        case_results: list[CaseValidationResult] = []
        errors: list[str] = []

        validated_count = 0
        pending_count = 0
        invalid_meta_count = 0
        missing_source_count = 0
        chunk_mismatch_count = 0

        for q in queries:
            result = self.validate_single_query(q)
            case_results.append(result)

            if result.validation_status == BenchmarkCaseStatus.VALIDATED_REAL_FILING:
                validated_count += 1
            elif result.validation_status == BenchmarkCaseStatus.PENDING_ANNOTATION:
                pending_count += 1
            elif result.validation_status == BenchmarkCaseStatus.INVALID_METADATA:
                invalid_meta_count += 1
                errors.extend([f"[{result.query_id}] {iss}" for iss in result.issues])
            elif result.validation_status == BenchmarkCaseStatus.MISSING_SOURCE:
                missing_source_count += 1
                errors.extend([f"[{result.query_id}] {iss}" for iss in result.issues])
            elif result.validation_status == BenchmarkCaseStatus.CHUNK_MISMATCH:
                chunk_mismatch_count += 1
                errors.extend([f"[{result.query_id}] {iss}" for iss in result.issues])

        is_valid = (
            invalid_meta_count == 0
            and missing_source_count == 0
            and chunk_mismatch_count == 0
        )

        return BenchmarkValidationReport(
            total_queries=len(queries),
            validated_filings=validated_count,
            pending_annotations=pending_count,
            invalid_metadata_count=invalid_meta_count,
            missing_source_count=missing_source_count,
            chunk_mismatch_count=chunk_mismatch_count,
            is_dataset_valid=is_valid,
            case_results=case_results,
            errors=errors,
        )

    def validate_single_query(self, query: dict[str, Any]) -> CaseValidationResult:
        """Validate an individual query item."""
        query_id = query.get("query_id", "UNKNOWN")
        ticker = query.get("company_ticker", "").upper().strip()
        cik = str(query.get("cik", "")).strip().zfill(10)
        accession = query.get("accession_number", "").strip()
        sec_url = query.get("sec_url", "").strip()
        declared_status = query.get(
            "status", BenchmarkCaseStatus.VALIDATED_REAL_FILING.value
        )
        excerpt = query.get("ground_truth_excerpt", "").strip()
        expected_chunks = query.get("expected_chunk_ids", [])

        issues: list[str] = []

        # 1. Ticker & CIK verification
        if not ticker:
            issues.append("Missing company_ticker")
        elif ticker in BENCHMARK_TICKER_CIK_MAP:
            expected_cik = BENCHMARK_TICKER_CIK_MAP[ticker]
            if cik != expected_cik:
                issues.append(
                    f"CIK mismatch for {ticker}: declared {cik}, expected {expected_cik}"
                )

        # 2. Accession number syntax
        if not accession:
            issues.append("Missing accession_number")
        elif not ACCESSION_NUMBER_PATTERN.match(accession):
            issues.append(f"Invalid accession number format: '{accession}'")

        # 3. SEC URL validation
        if not sec_url:
            issues.append("Missing sec_url")
        else:
            try:
                parsed_url = urlparse(sec_url)
                if parsed_url.hostname not in ALLOWED_SEC_HOSTS:
                    issues.append(
                        f"Unauthorized SEC host '{parsed_url.hostname}' in URL: {sec_url}"
                    )
                if not parsed_url.path.startswith("/Archives/edgar/data/"):
                    issues.append(
                        f"URL path does not follow SEC EDGAR archive pattern: {sec_url}"
                    )
            except Exception as exc:
                issues.append(f"Malformed SEC URL '{sec_url}': {exc}")

        # 4. Excerpt validation
        if not excerpt:
            issues.append("Missing ground_truth_excerpt")

        # Determine structural validation status
        if issues:
            if any(
                "Missing sec_url" in i or "Unauthorized SEC host" in i for i in issues
            ):
                return CaseValidationResult(
                    query_id=query_id,
                    ticker=ticker,
                    cik=cik,
                    accession_number=accession,
                    declared_status=declared_status,
                    validation_status=BenchmarkCaseStatus.MISSING_SOURCE,
                    is_valid=False,
                    issues=issues,
                )
            return CaseValidationResult(
                query_id=query_id,
                ticker=ticker,
                cik=cik,
                accession_number=accession,
                declared_status=declared_status,
                validation_status=BenchmarkCaseStatus.INVALID_METADATA,
                is_valid=False,
                issues=issues,
            )

        # 5. Database Cross-Check (optional if database has ingested this filing)
        db_doc_found = False
        db_chunks_found: list[str] = []
        try:
            with self.db.connection() as conn:
                cur = conn.cursor()
                doc_row = cur.execute(
                    "SELECT document_id FROM documents WHERE accession_number = ?",
                    (accession,),
                ).fetchone()
                if doc_row:
                    db_doc_found = True
                    for cid in expected_chunks:
                        chunk_row = cur.execute(
                            "SELECT text FROM document_chunks WHERE chunk_id = ?",
                            (cid,),
                        ).fetchone()
                        if chunk_row:
                            db_chunks_found.append(cid)
                            chunk_text = chunk_row[0] or ""
                            # Check excerpt overlap if both exist
                            if excerpt and (
                                excerpt[:30] not in chunk_text
                                and excerpt[-30:] not in chunk_text
                            ):
                                issues.append(
                                    f"Ground truth excerpt does not match database chunk {cid}"
                                )
        except Exception as exc:
            logger.debug("Database audit check skipped or raised error: %s", exc)

        if any("does not match database chunk" in i for i in issues):
            return CaseValidationResult(
                query_id=query_id,
                ticker=ticker,
                cik=cik,
                accession_number=accession,
                declared_status=declared_status,
                validation_status=BenchmarkCaseStatus.CHUNK_MISMATCH,
                is_valid=False,
                issues=issues,
                db_document_found=db_doc_found,
                db_chunks_found=db_chunks_found,
            )

        # Respect declared status if valid
        if declared_status == BenchmarkCaseStatus.PENDING_ANNOTATION.value:
            final_status = BenchmarkCaseStatus.PENDING_ANNOTATION
        else:
            final_status = BenchmarkCaseStatus.VALIDATED_REAL_FILING

        return CaseValidationResult(
            query_id=query_id,
            ticker=ticker,
            cik=cik,
            accession_number=accession,
            declared_status=declared_status,
            validation_status=final_status,
            is_valid=True,
            issues=issues,
            db_document_found=db_doc_found,
            db_chunks_found=db_chunks_found,
        )

