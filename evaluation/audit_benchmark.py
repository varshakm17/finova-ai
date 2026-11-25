"""Real SEC Benchmark Integrity Auditor.

Performs a rigorous, evidence-based audit of all 24 queries in the real SEC benchmark dataset,
validating ticker/CIK alignment, SEC submissions metadata presence, live HTTP URL resolution,
database filing presence, chunk ID existence, and ground-truth excerpt traceability.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.data.sec_client import SECClient
from config.settings import get_settings

BENCHMARK_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "TSLA": "0001318605",
    "NVDA": "0001045810",
}

ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
ALLOWED_SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "sec.gov"}


def audit_benchmark(
    benchmark_path: Path | str | None = None,
    db_path: Path | str | None = None,
    output_json_path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute complete benchmark audit against SEC EDGAR and local database."""
    bench_file = Path(benchmark_path or PROJECT_ROOT / "evaluation" / "datasets" / "real_sec_benchmark.json")
    database_file = Path(db_path or PROJECT_ROOT / "finova.db")
    out_file = Path(output_json_path or PROJECT_ROOT / "reports" / "validation" / "session18_benchmark_integrity.json")

    with open(bench_file, encoding="utf-8") as f:
        data = json.load(f)

    queries: list[dict[str, Any]] = data.get("queries", [])
    settings = get_settings()
    sec_client = SECClient(settings=settings)

    # Cache SEC filings list per CIK to avoid redundant API calls
    submissions_cache: dict[str, list[dict[str, Any]]] = {}
    for ticker, cik in BENCHMARK_CIKS.items():
        try:
            submissions_cache[cik] = sec_client.get_company_filings(cik)
            time.sleep(0.15)
        except Exception:
            submissions_cache[cik] = []

    # Database connection
    con = sqlite3.connect(database_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    audit_records: list[dict[str, Any]] = []
    classification_counts = {
        "VERIFIED_SOURCE_AND_CHUNKS": 0,
        "VERIFIED_SOURCE_MISSING_CHUNKS": 0,
        "INVALID_SOURCE_METADATA": 0,
        "INVALID_CHUNK_MAPPING": 0,
        "PENDING_ANNOTATION": 0,
    }

    headers = {"User-Agent": settings.SEC_USER_AGENT}
    with httpx.Client(headers=headers, timeout=12.0) as http_client:
        for q in queries:
            qid = q.get("query_id", "UNKNOWN")
            ticker = q.get("company_ticker", "").strip().upper()
            cik = str(q.get("cik", "")).strip().zfill(10)
            accession = q.get("accession_number", "").strip()
            sec_url = q.get("sec_url", "").strip()
            declared_status = q.get("status", "")
            _section = q.get("expected_section", "")
            chunk_ids = q.get("expected_chunk_ids", [])
            excerpt = q.get("ground_truth_excerpt", "").strip()

            issues: list[str] = []
            metadata_valid = True

            # 1. Ticker & CIK correspondence
            if ticker not in BENCHMARK_CIKS or BENCHMARK_CIKS[ticker] != cik:
                issues.append(f"CIK mismatch: {ticker} has CIK {cik}, expected {BENCHMARK_CIKS.get(ticker)}")
                metadata_valid = False

            # 2. Accession syntax
            if not ACCESSION_PATTERN.match(accession):
                issues.append(f"Invalid accession number format: '{accession}'")
                metadata_valid = False

            # 3. Accession presence in SEC submissions metadata
            cik_filings = submissions_cache.get(cik, [])
            matching_filing = next((f for f in cik_filings if f.get("accession_number") == accession), None)
            if not matching_filing:
                issues.append(f"Accession {accession} not found in SEC EDGAR submissions for {ticker} (CIK {cik})")
                metadata_valid = False

            # 4. SEC URL validation and live HTTP check
            url_resolves = False
            http_status = None
            try:
                parsed_url = urlparse(sec_url)
                if parsed_url.hostname not in ALLOWED_SEC_HOSTS or not parsed_url.path.startswith("/Archives/edgar/data/"):
                    issues.append(f"Invalid SEC URL structure: '{sec_url}'")
                    metadata_valid = False
                else:
                    time.sleep(0.12)  # SEC rate limit compliance
                    resp = http_client.head(sec_url)
                    http_status = resp.status_code
                    if resp.status_code == 200:
                        url_resolves = True
                    else:
                        issues.append(f"SEC URL does not resolve (HTTP {resp.status_code}): {sec_url}")
                        metadata_valid = False
            except Exception as exc:
                issues.append(f"Failed to verify SEC URL: {exc}")
                metadata_valid = False

            # 5. Excerpt presence
            if not excerpt:
                issues.append("Ground truth excerpt is empty")

            # 6. Database checks
            db_document_found = False
            db_chunks_found: list[str] = []
            db_chunks_belong_to_filing = True
            excerpt_found_in_chunk = False

            try:
                doc_row = cur.execute(
                    "SELECT document_id, ticker, accession_number FROM documents WHERE accession_number = ?",
                    (accession,),
                ).fetchone()
                if doc_row:
                    db_document_found = True

                for cid in chunk_ids:
                    c_row = cur.execute(
                        "SELECT chunk_id, document_id, ticker, accession_number, section_identifier, chunk_text FROM document_chunks WHERE chunk_id = ?",
                        (cid,),
                    ).fetchone()
                    if c_row:
                        db_chunks_found.append(cid)
                        if c_row["accession_number"] != accession or c_row["ticker"] != ticker:
                            db_chunks_belong_to_filing = False
                        if excerpt and excerpt[:40] in c_row["chunk_text"]:
                            excerpt_found_in_chunk = True
                if excerpt and db_chunks_found and not excerpt_found_in_chunk:
                    issues.append("Ground truth excerpt not found in referenced database chunk text.")
            except Exception as exc:
                issues.append(f"Database query error: {exc}")

            # 7. Final Classification
            classification: str
            if not metadata_valid:
                classification = "INVALID_SOURCE_METADATA"
            elif declared_status == "pending_annotation":
                classification = "PENDING_ANNOTATION"
            elif db_document_found and len(db_chunks_found) == len(chunk_ids) and len(chunk_ids) > 0 and db_chunks_belong_to_filing:
                classification = "VERIFIED_SOURCE_AND_CHUNKS"
            elif db_document_found and (len(db_chunks_found) < len(chunk_ids) or not db_chunks_belong_to_filing):
                classification = "INVALID_CHUNK_MAPPING"
            else:
                # Source metadata verified on SEC EDGAR, but filing/chunks not yet persisted in local DB
                classification = "VERIFIED_SOURCE_MISSING_CHUNKS"

            classification_counts[classification] += 1

            audit_records.append({
                "query_id": qid,
                "ticker": ticker,
                "cik": cik,
                "accession_number": accession,
                "sec_url": sec_url,
                "http_status": http_status,
                "declared_status": declared_status,
                "classification": classification,
                "is_source_metadata_valid": metadata_valid,
                "url_resolves": url_resolves,
                "db_document_found": db_document_found,
                "expected_chunk_ids": chunk_ids,
                "db_chunks_found": db_chunks_found,
                "is_placeholder_chunk": any(cid.startswith("real_chunk_") for cid in chunk_ids),
                "issues": issues,
            })

    con.close()

    report_payload = {
        "audit_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries": len(queries),
        "classification_summary": classification_counts,
        "queries": audit_records,
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    return report_payload


if __name__ == "__main__":
    rep = audit_benchmark()
    print("=" * 60)
    print("BENCHMARK INTEGRITY AUDIT COMPLETE")
    print("=" * 60)
    print("Total queries:", rep["total_queries"])
    print("Classification Summary:")
    for k, v in rep["classification_summary"].items():
        print(f"  {k}: {v}")
    print("\nSaved report to: reports/validation/session18_benchmark_integrity.json")
