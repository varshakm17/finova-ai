"""SQLite Storage Engine for Finova AI.

Provides persistent schema management, foreign key relationships,
upsert transactions, and querying for companies, filings, and financial metrics.
"""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.data.data_normalizer import FinancialObservation
from backend.data.sec_client import normalize_cik
from backend.utils.logger import get_logger
from config.settings import BASE_DIR, Settings, get_settings

logger = get_logger("storage")


def get_db_file_path(settings: Settings | None = None) -> str:
    """Resolve database path from application settings.

    Returns:
        str: Absolute file path or ':memory:'.
    """
    cfg = settings or get_settings()
    url = cfg.DATABASE_URL
    if url.startswith("sqlite:///"):
        rel_or_abs = url.replace("sqlite:///", "")
        if rel_or_abs == ":memory:":
            return ":memory:"
        path = Path(rel_or_abs)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    return str(BASE_DIR / "finova.db")


class Database:
    """Manages SQLite connections, schema initialization, and transactional data operations."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_db_file_path()
        self._memory_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON;")
        self.init_db()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual connection with foreign keys enabled and row factory configured."""
        if self._memory_conn is not None:
            try:
                yield self._memory_conn
                self._memory_conn.commit()
            except Exception:
                self._memory_conn.rollback()
                raise
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init_db(self) -> None:
        """Create necessary database tables and performance indexes if not present."""
        with self.connection() as conn:
            cursor = conn.cursor()

            # 1. Companies Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    cik TEXT PRIMARY KEY,
                    ticker TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    sic TEXT,
                    sic_description TEXT,
                    fiscal_year_end TEXT,
                    state_location TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # 2. Filings Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS filings (
                    accession_number TEXT PRIMARY KEY,
                    cik TEXT NOT NULL,
                    form TEXT NOT NULL,
                    filing_date TEXT NOT NULL,
                    report_date TEXT,
                    acceptance_date TEXT,
                    primary_document TEXT,
                    primary_doc_description TEXT,
                    is_xbrl INTEGER DEFAULT 0,
                    is_inline_xbrl INTEGER DEFAULT 0,
                    url TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (cik) REFERENCES companies (cik) ON DELETE CASCADE
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_filings_cik ON filings (cik);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_filings_form ON filings (form);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_filings_date ON filings (filing_date);"
            )

            # 3. Financial Observations Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cik TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    statement_type TEXT NOT NULL,
                    original_tag TEXT NOT NULL,
                    numeric_value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    period_start TEXT NOT NULL DEFAULT '',
                    period_end TEXT NOT NULL,
                    duration_days INTEGER,
                    period_type TEXT NOT NULL,
                    fiscal_year INTEGER,
                    fiscal_period TEXT,
                    filing_date TEXT NOT NULL,
                    filing_type TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (cik) REFERENCES companies (cik) ON DELETE CASCADE,
                    UNIQUE(cik, metric_name, period_end, period_type, period_start)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_cik_metric ON financial_observations (cik, metric_name);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_ticker ON financial_observations (ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_period_end ON financial_observations (period_end);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_fy ON financial_observations (fiscal_year);"
            )

            # 4. Financial Calculations Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_calculations (
                    calculation_id TEXT PRIMARY KEY,
                    cik TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    calculated_value REAL,
                    unit TEXT NOT NULL,
                    period_type TEXT NOT NULL,
                    period_start TEXT NOT NULL DEFAULT '',
                    period_end TEXT NOT NULL,
                    fiscal_year INTEGER,
                    fiscal_period TEXT,
                    formula_name TEXT NOT NULL,
                    formula_expression TEXT NOT NULL,
                    calculation_status TEXT NOT NULL,
                    unavailable_reason TEXT,
                    input_observations_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    FOREIGN KEY (cik) REFERENCES companies (cik) ON DELETE CASCADE,
                    UNIQUE(cik, metric_name, period_end, period_type, period_start)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_calc_ticker ON financial_calculations (ticker, metric_name);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_calc_cik ON financial_calculations (cik);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_calc_period ON financial_calculations (period_end, period_type);"
            )

            # 5. Research Answers Table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS research_answers (
                    answer_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    ticker TEXT,
                    answer_text TEXT NOT NULL,
                    answer_status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    retrieval_method TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    retrieved_evidence_json TEXT NOT NULL,
                    calculation_evidence_json TEXT NOT NULL,
                    generation_metadata_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_answers_ticker ON research_answers (ticker);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_answers_created_at ON research_answers (created_at);"
            )

            # 6. Verification Runs Table (Session 09)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_runs (
                    run_id TEXT PRIMARY KEY,
                    answer_id TEXT NOT NULL,
                    overall_status TEXT NOT NULL,
                    total_claims INTEGER NOT NULL,
                    supported_claims INTEGER NOT NULL,
                    partially_supported_claims INTEGER NOT NULL,
                    unsupported_claims INTEGER NOT NULL,
                    contradicted_claims INTEGER NOT NULL,
                    not_verifiable_claims INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    verifier_version TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_vruns_answer_id ON verification_runs (answer_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_vruns_verified_at ON verification_runs (verified_at);"
            )

            # 7. Answer Claims Table (Session 09)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_claims (
                    claim_id TEXT NOT NULL,
                    answer_id TEXT NOT NULL,
                    claim_text TEXT NOT NULL,
                    claim_type TEXT NOT NULL,
                    numeric_values_json TEXT NOT NULL,
                    mentioned_company TEXT,
                    mentioned_period TEXT,
                    citation_ids_json TEXT NOT NULL,
                    is_verifiable INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (claim_id, answer_id)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_answer_id ON answer_claims (answer_id);"
            )

            # 8. Claim Verification Results Table (Session 09)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_verification_results (
                    result_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    supporting_evidence_json TEXT NOT NULL,
                    contradicting_evidence_json TEXT NOT NULL,
                    verification_reason TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    verification_method TEXT NOT NULL,
                    numeric_check_json TEXT,
                    period_check_json TEXT,
                    contradiction_check_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cvr_run_id ON claim_verification_results (run_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cvr_claim_id ON claim_verification_results (claim_id);"
            )

            # 9. Verification Issues Table (Session 09)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_issues (
                    issue_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    claim_id TEXT,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_reference TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_vissues_run_id ON verification_issues (run_id);"
            )

            # 10. Agent Workflows Table (Session 10)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_workflows (
                    request_id TEXT PRIMARY KEY,
                    user_question TEXT NOT NULL,
                    company_ticker TEXT,
                    intent TEXT NOT NULL,
                    workflow_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    final_answer TEXT,
                    verification_status TEXT,
                    retrieved_evidence_count INTEGER NOT NULL DEFAULT 0,
                    calculation_receipts_count INTEGER NOT NULL DEFAULT 0,
                    total_duration_ms REAL NOT NULL DEFAULT 0.0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aw_created_at ON agent_workflows (created_at);"
            )

            # 11. Agent Execution Events Table (Session 10)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_execution_events (
                    event_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    input_summary TEXT,
                    output_summary TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (request_id) REFERENCES agent_workflows(request_id)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aee_request_id ON agent_execution_events (request_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_aee_step_index ON agent_execution_events (request_id, step_index);"
            )

        logger.info("Database initialized successfully at: %s", self.db_path)

    def save_company(self, company_data: dict[str, Any]) -> None:
        """Upsert company identity and metadata record."""
        cik = normalize_cik(company_data["cik"])
        ticker = company_data["ticker"].strip().upper()
        name = company_data["name"].strip()
        now_iso = datetime.now(UTC).isoformat()

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO companies (
                    cik, ticker, name, sic, sic_description,
                    fiscal_year_end, state_location, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cik) DO UPDATE SET
                    ticker = excluded.ticker,
                    name = excluded.name,
                    sic = COALESCE(excluded.sic, companies.sic),
                    sic_description = COALESCE(excluded.sic_description, companies.sic_description),
                    fiscal_year_end = COALESCE(excluded.fiscal_year_end, companies.fiscal_year_end),
                    state_location = COALESCE(excluded.state_location, companies.state_location),
                    updated_at = excluded.updated_at;
                """,
                (
                    cik,
                    ticker,
                    name,
                    company_data.get("sic"),
                    company_data.get("sic_description"),
                    company_data.get("fiscal_year_end"),
                    company_data.get("state_location"),
                    now_iso,
                ),
            )

    def get_company_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        """Retrieve company metadata by ticker."""
        norm_ticker = ticker.strip().upper().replace(".", "-")
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE ticker = ?;", (norm_ticker,)
            ).fetchone()
            return dict(row) if row else None

    def get_company_by_cik(self, cik: str | int) -> dict[str, Any] | None:
        """Retrieve company metadata by 10-digit CIK."""
        norm_cik = normalize_cik(cik)
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE cik = ?;", (norm_cik,)
            ).fetchone()
            return dict(row) if row else None

    def save_filings(self, cik: str, filings: list[dict[str, Any]]) -> int:
        """Upsert batch of filing records for a company.

        Returns:
            int: Count of filings successfully inserted or updated.
        """
        norm_cik = normalize_cik(cik)
        now_iso = datetime.now(UTC).isoformat()

        records = [
            (
                f["accession_number"],
                norm_cik,
                f["form"],
                f["filing_date"],
                f.get("report_date"),
                f.get("acceptance_date"),
                f.get("primary_document"),
                f.get("primary_doc_description"),
                1 if f.get("is_xbrl") else 0,
                1 if f.get("is_inline_xbrl") else 0,
                f.get("url"),
                now_iso,
            )
            for f in filings
            if f.get("accession_number")
        ]

        if not records:
            return 0

        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO filings (
                    accession_number, cik, form, filing_date, report_date,
                    acceptance_date, primary_document, primary_doc_description,
                    is_xbrl, is_inline_xbrl, url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(accession_number) DO UPDATE SET
                    form = excluded.form,
                    filing_date = excluded.filing_date,
                    report_date = excluded.report_date,
                    primary_document = excluded.primary_document,
                    url = excluded.url;
                """,
                records,
            )
        return len(records)

    def get_filings(
        self,
        cik: str,
        form_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query filings metadata by CIK and optional form filter."""
        norm_cik = normalize_cik(cik)
        query = "SELECT * FROM filings WHERE cik = ?"
        params: list[Any] = [norm_cik]

        if form_type:
            query += " AND form = ?"
            params.append(form_type.upper().strip())

        query += " ORDER BY filing_date DESC, accession_number DESC LIMIT ?;"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def save_financial_observations(
        self, observations: list[FinancialObservation]
    ) -> int:
        """Upsert batch of canonical financial observations with duplicate protection.

        Returns:
            int: Count of observations processed.
        """
        if not observations:
            return 0

        now_iso = datetime.now(UTC).isoformat()
        records = [
            (
                obs.company_cik,
                obs.company_ticker,
                obs.company_name,
                obs.metric_name,
                obs.statement_type,
                obs.original_tag,
                obs.numeric_value,
                obs.unit,
                obs.period_start or "",
                obs.period_end,
                obs.duration_days,
                obs.period_type,
                obs.fiscal_year,
                obs.fiscal_period,
                obs.filing_date,
                obs.filing_type,
                obs.accession_number,
                obs.source_url,
                now_iso,
            )
            for obs in observations
        ]

        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO financial_observations (
                    cik, ticker, company_name, metric_name, statement_type,
                    original_tag, numeric_value, unit, period_start, period_end,
                    duration_days, period_type, fiscal_year, fiscal_period,
                    filing_date, filing_type, accession_number, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cik, metric_name, period_end, period_type, period_start) DO UPDATE SET
                    numeric_value = excluded.numeric_value,
                    original_tag = excluded.original_tag,
                    filing_date = excluded.filing_date,
                    accession_number = excluded.accession_number,
                    source_url = excluded.source_url;
                """,
                records,
            )
        return len(records)

    def get_financial_observations(
        self,
        ticker_or_cik: str,
        start_year: int | None = None,
        end_year: int | None = None,
        period_type: str | None = None,
        metric_name: str | None = None,
        limit: int = 1000,
    ) -> list[FinancialObservation]:
        """Query canonical financial observations with optional filters."""
        query = "SELECT * FROM financial_observations WHERE (ticker = ? OR cik = ?)"
        params: list[Any] = [ticker_or_cik.upper().strip(), ticker_or_cik.strip()]

        if start_year is not None:
            query += " AND (fiscal_year >= ? OR substr(period_end, 1, 4) >= ?)"
            params.extend([start_year, str(start_year)])

        if end_year is not None:
            query += " AND (fiscal_year <= ? OR substr(period_end, 1, 4) <= ?)"
            params.extend([end_year, str(end_year)])

        if period_type is not None:
            query += " AND period_type = ?"
            params.append(period_type.lower().strip())

        if metric_name is not None:
            query += " AND lower(metric_name) = lower(?)"
            params.append(metric_name.strip())

        query += " ORDER BY period_end DESC, metric_name ASC LIMIT ?;"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results: list[FinancialObservation] = []
            for row in rows:
                results.append(
                    FinancialObservation(
                        company_ticker=row["ticker"],
                        company_cik=row["cik"],
                        company_name=row["company_name"],
                        metric_name=row["metric_name"],
                        statement_type=row["statement_type"],
                        original_tag=row["original_tag"],
                        numeric_value=row["numeric_value"],
                        unit=row["unit"],
                        period_start=(
                            row["period_start"] if row["period_start"] else None
                        ),
                        period_end=row["period_end"],
                        duration_days=row["duration_days"],
                        period_type=row["period_type"],
                        fiscal_year=row["fiscal_year"],
                        fiscal_period=row["fiscal_period"],
                        filing_date=row["filing_date"],
                        filing_type=row["filing_type"],
                        accession_number=row["accession_number"],
                        source_url=row["source_url"],
                    )
                )
            return results

    def save_financial_calculations(self, calculations: list[dict[str, Any]]) -> int:
        """Upsert calculated financial metrics and receipts into financial_calculations table.

        Args:
            calculations: List of calculation dictionaries or CalculationReceipt data.

        Returns:
            int: Number of calculation records saved.
        """
        if not calculations:
            return 0

        records = [
            (
                c["calculation_id"],
                c["cik"],
                c["ticker"].upper().strip(),
                c["company_name"],
                c["metric_name"],
                c.get("calculated_value"),
                c["unit"],
                c["period_type"],
                c.get("period_start") or "",
                c["period_end"],
                c.get("fiscal_year"),
                c.get("fiscal_period"),
                c["formula_name"],
                c["formula_expression"],
                c["status"]
                if "status" in c
                else c.get("calculation_status", "calculated"),
                c.get("unavailable_reason"),
                (
                    json.dumps(c["inputs"])
                    if "inputs" in c and not isinstance(c["inputs"], str)
                    else json.dumps(c.get("input_observations", []))
                    if not isinstance(c.get("input_observations", []), str)
                    else c.get("input_observations", "[]")
                ),
                (
                    json.dumps(c["warnings"])
                    if not isinstance(c.get("warnings", []), str)
                    else c.get("warnings", "[]")
                ),
                c.get("calculated_at") or datetime.now(UTC).isoformat(),
            )
            for c in calculations
        ]

        with self.connection() as conn:
            conn.executemany(
                """
                INSERT INTO financial_calculations (
                    calculation_id, cik, ticker, company_name, metric_name,
                    calculated_value, unit, period_type, period_start, period_end,
                    fiscal_year, fiscal_period, formula_name, formula_expression,
                    calculation_status, unavailable_reason, input_observations_json,
                    warnings_json, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cik, metric_name, period_end, period_type, period_start) DO UPDATE SET
                    calculated_value = excluded.calculated_value,
                    calculation_status = excluded.calculation_status,
                    unavailable_reason = excluded.unavailable_reason,
                    input_observations_json = excluded.input_observations_json,
                    warnings_json = excluded.warnings_json,
                    calculated_at = excluded.calculated_at;
                """,
                records,
            )
        return len(records)

    def get_financial_calculations(
        self,
        ticker_or_cik: str,
        metric_name: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        period_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Query calculated financial metrics with optional filters."""
        query = "SELECT * FROM financial_calculations WHERE (ticker = ? OR cik = ?)"
        params: list[Any] = [ticker_or_cik.upper().strip(), ticker_or_cik.strip()]

        if start_year is not None:
            query += " AND (fiscal_year >= ? OR substr(period_end, 1, 4) >= ?)"
            params.extend([start_year, str(start_year)])

        if end_year is not None:
            query += " AND (fiscal_year <= ? OR substr(period_end, 1, 4) <= ?)"
            params.extend([end_year, str(end_year)])

        if period_type is not None:
            query += " AND period_type = ?"
            params.append(period_type.lower().strip())

        if metric_name is not None:
            query += " AND lower(metric_name) = lower(?)"
            params.append(metric_name.strip())

        query += " ORDER BY period_end DESC, metric_name ASC LIMIT ?;"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                r_dict = dict(row)
                # Map column name calculation_status to status for API consistency
                if "calculation_status" in r_dict:
                    r_dict["status"] = r_dict["calculation_status"]
                try:
                    r_dict["inputs"] = json.loads(
                        r_dict.pop("input_observations_json", "[]")
                    )
                except (json.JSONDecodeError, TypeError):
                    r_dict["inputs"] = []
                try:
                    r_dict["warnings"] = json.loads(r_dict.pop("warnings_json", "[]"))
                except (json.JSONDecodeError, TypeError):
                    r_dict["warnings"] = []
                results.append(r_dict)
            return results

    def get_financial_calculation_by_id(
        self, calculation_id: str
    ) -> dict[str, Any] | None:
        """Fetch a specific calculation receipt by its unique calculation_id."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM financial_calculations WHERE calculation_id = ?;",
                (calculation_id.strip(),),
            ).fetchone()
            if not row:
                return None
            r_dict = dict(row)
            if "calculation_status" in r_dict:
                r_dict["status"] = r_dict["calculation_status"]
            try:
                r_dict["inputs"] = json.loads(
                    r_dict.pop("input_observations_json", "[]")
                )
            except (json.JSONDecodeError, TypeError):
                r_dict["inputs"] = []
            try:
                r_dict["warnings"] = json.loads(r_dict.pop("warnings_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                r_dict["warnings"] = []
            return r_dict

    def save_research_answer(self, answer_data: dict[str, Any]) -> None:
        """Persist a synthesized RAG research answer and its provenance trail."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO research_answers (
                    answer_id, question, ticker, answer_text, answer_status,
                    provider, model_name, retrieval_method, citations_json,
                    retrieved_evidence_json, calculation_evidence_json,
                    generation_metadata_json, warnings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(answer_id) DO UPDATE SET
                    answer_text = excluded.answer_text,
                    answer_status = excluded.answer_status,
                    citations_json = excluded.citations_json,
                    warnings_json = excluded.warnings_json;
                """,
                (
                    answer_data["answer_id"],
                    answer_data["question"],
                    answer_data.get("ticker"),
                    answer_data.get("answer_text") or answer_data.get("answer", ""),
                    answer_data["answer_status"],
                    answer_data["provider"],
                    answer_data["model_name"],
                    answer_data.get("retrieval_method", "hybrid"),
                    json.dumps(answer_data.get("citations", [])),
                    json.dumps(answer_data.get("retrieved_evidence", [])),
                    json.dumps(answer_data.get("calculation_evidence", [])),
                    json.dumps(answer_data.get("generation_metadata", {})),
                    json.dumps(answer_data.get("warnings", [])),
                    answer_data.get("created_at") or datetime.now(UTC).isoformat(),
                ),
            )

    def get_research_answer(self, answer_id: str) -> dict[str, Any] | None:
        """Fetch a saved research answer by its unique answer_id."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM research_answers WHERE answer_id = ?;",
                (answer_id.strip(),),
            ).fetchone()
            if not row:
                return None
            r_dict = dict(row)
            r_dict["answer"] = r_dict["answer_text"]
            for field_name, json_col in [
                ("citations", "citations_json"),
                ("retrieved_evidence", "retrieved_evidence_json"),
                ("calculation_evidence", "calculation_evidence_json"),
                ("generation_metadata", "generation_metadata_json"),
                ("warnings", "warnings_json"),
            ]:
                try:
                    r_dict[field_name] = json.loads(
                        r_dict.pop(
                            json_col,
                            "[]"
                            if "json" in json_col and "metadata" not in json_col
                            else "{}",
                        )
                    )
                except (json.JSONDecodeError, TypeError):
                    r_dict[field_name] = [] if "metadata" not in field_name else {}
            return r_dict

    def list_research_answers(
        self, ticker: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """List recently saved research answers, optionally filtered by ticker."""
        query = "SELECT * FROM research_answers"
        params: list[Any] = []
        if ticker:
            query += " WHERE ticker = ?"
            params.append(ticker.strip().upper())
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                r_dict = dict(row)
                r_dict["answer"] = r_dict["answer_text"]
                for field_name, json_col in [
                    ("citations", "citations_json"),
                    ("retrieved_evidence", "retrieved_evidence_json"),
                    ("calculation_evidence", "calculation_evidence_json"),
                    ("generation_metadata", "generation_metadata_json"),
                    ("warnings", "warnings_json"),
                ]:
                    try:
                        r_dict[field_name] = json.loads(
                            r_dict.pop(
                                json_col,
                                "[]"
                                if "json" in json_col and "metadata" not in json_col
                                else "{}",
                            )
                        )
                    except (json.JSONDecodeError, TypeError):
                        r_dict[field_name] = [] if "metadata" not in field_name else {}
                results.append(r_dict)
            return results

    def save_verification_run(self, run_data: dict[str, Any]) -> None:
        """Persist a complete answer verification run, claims, and audit details."""
        run_id = run_data["run_id"]
        answer_id = run_data["answer_id"]
        now_iso = run_data.get("verified_at") or datetime.now(UTC).isoformat()

        with self.connection() as conn:
            # 1. Verification Run Record
            raw_status = run_data["overall_status"]
            if hasattr(raw_status, "value"):
                status_val = raw_status.value
            else:
                s_str = str(raw_status)
                status_val = (
                    s_str.split(".")[-1].lower() if "." in s_str else s_str.lower()
                )

            conn.execute(
                """
                INSERT INTO verification_runs (
                    run_id, answer_id, overall_status, total_claims, supported_claims,
                    partially_supported_claims, unsupported_claims, contradicted_claims,
                    not_verifiable_claims, warnings_json, verified_at, verifier_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    overall_status = excluded.overall_status,
                    total_claims = excluded.total_claims,
                    supported_claims = excluded.supported_claims,
                    partially_supported_claims = excluded.partially_supported_claims,
                    unsupported_claims = excluded.unsupported_claims,
                    contradicted_claims = excluded.contradicted_claims,
                    not_verifiable_claims = excluded.not_verifiable_claims,
                    warnings_json = excluded.warnings_json,
                    verified_at = excluded.verified_at;
                """,
                (
                    run_id,
                    answer_id,
                    status_val,
                    int(run_data.get("total_claims", 0)),
                    int(run_data.get("supported_claims", 0)),
                    int(run_data.get("partially_supported_claims", 0)),
                    int(run_data.get("unsupported_claims", 0)),
                    int(run_data.get("contradicted_claims", 0)),
                    int(run_data.get("not_verifiable_claims", 0)),
                    json.dumps(run_data.get("warnings", [])),
                    now_iso,
                    str(run_data.get("verifier_version", "0.1.0")),
                ),
            )

            # 2. Claim-level verification results & answer claims
            for cr in run_data.get("claim_results", []):
                claim_id = cr["claim_id"]
                result_id = f"{run_id}_{claim_id}"

                raw_outcome = cr["outcome"]
                if hasattr(raw_outcome, "value"):
                    outcome_val = raw_outcome.value
                else:
                    o_str = str(raw_outcome)
                    outcome_val = (
                        o_str.split(".")[-1].lower() if "." in o_str else o_str.lower()
                    )

                # Insert/update answer_claims
                conn.execute(
                    """
                    INSERT INTO answer_claims (
                        claim_id, answer_id, claim_text, claim_type, numeric_values_json,
                        mentioned_company, mentioned_period, citation_ids_json,
                        is_verifiable, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(claim_id, answer_id) DO UPDATE SET
                        claim_text = excluded.claim_text,
                        claim_type = excluded.claim_type,
                        numeric_values_json = excluded.numeric_values_json,
                        citation_ids_json = excluded.citation_ids_json;
                    """,
                    (
                        claim_id,
                        answer_id,
                        cr.get("claim_text", ""),
                        str(cr.get("claim_type", "general_fact")),
                        json.dumps(cr.get("numeric_values", [])),
                        cr.get("mentioned_company"),
                        cr.get("mentioned_period"),
                        json.dumps(cr.get("citation_ids", [])),
                        1 if cr.get("is_verifiable", True) else 0,
                        now_iso,
                    ),
                )

                # Insert/update claim_verification_results
                conn.execute(
                    """
                    INSERT INTO claim_verification_results (
                        result_id, run_id, claim_id, outcome, supporting_evidence_json,
                        contradicting_evidence_json, verification_reason, confidence_score,
                        verification_method, numeric_check_json, period_check_json,
                        contradiction_check_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(result_id) DO UPDATE SET
                        outcome = excluded.outcome,
                        verification_reason = excluded.verification_reason,
                        confidence_score = excluded.confidence_score,
                        verification_method = excluded.verification_method;
                    """,
                    (
                        result_id,
                        run_id,
                        claim_id,
                        outcome_val,
                        json.dumps(cr.get("supporting_evidence_ids", [])),
                        json.dumps(cr.get("contradicting_evidence_ids", [])),
                        cr.get("verification_reason", ""),
                        float(cr.get("confidence_score", 1.0)),
                        str(cr.get("verification_method", "unknown")),
                        json.dumps(cr.get("numeric_check"))
                        if cr.get("numeric_check")
                        else None,
                        json.dumps(cr.get("period_check"))
                        if cr.get("period_check")
                        else None,
                        json.dumps(cr.get("contradiction_check"))
                        if cr.get("contradiction_check")
                        else None,
                        now_iso,
                    ),
                )

    def get_verification_run(self, run_id: str) -> dict[str, Any] | None:
        """Fetch a complete verification run by run_id with all claim results."""
        with self.connection() as conn:
            run_row = conn.execute(
                "SELECT * FROM verification_runs WHERE run_id = ?;",
                (run_id.strip(),),
            ).fetchone()
            if not run_row:
                return None

            run_dict = dict(run_row)
            if "OverallVerificationStatus." in str(run_dict.get("overall_status")):
                run_dict["overall_status"] = (
                    str(run_dict["overall_status"]).split(".")[-1].lower()
                )
            try:
                run_dict["warnings"] = json.loads(run_dict.pop("warnings_json", "[]"))
            except (json.JSONDecodeError, TypeError):
                run_dict["warnings"] = []

            # Fetch claim results
            c_rows = conn.execute(
                """
                SELECT cvr.*, ac.claim_text, ac.claim_type, ac.mentioned_company,
                       ac.mentioned_period, ac.citation_ids_json, ac.is_verifiable
                FROM claim_verification_results cvr
                LEFT JOIN answer_claims ac ON cvr.claim_id = ac.claim_id AND ac.answer_id = ?
                WHERE cvr.run_id = ?
                ORDER BY cvr.claim_id ASC;
                """,
                (run_dict["answer_id"], run_id.strip()),
            ).fetchall()

            claim_results: list[dict[str, Any]] = []
            for cr in c_rows:
                c_dict = dict(cr)
                if "VerificationOutcome." in str(c_dict.get("outcome")):
                    c_dict["outcome"] = str(c_dict["outcome"]).split(".")[-1].lower()
                try:
                    c_dict["supporting_evidence_ids"] = json.loads(
                        c_dict.pop("supporting_evidence_json", "[]")
                    )
                except (json.JSONDecodeError, TypeError):
                    c_dict["supporting_evidence_ids"] = []
                try:
                    c_dict["contradicting_evidence_ids"] = json.loads(
                        c_dict.pop("contradicting_evidence_json", "[]")
                    )
                except (json.JSONDecodeError, TypeError):
                    c_dict["contradicting_evidence_ids"] = []
                try:
                    c_dict["citation_ids"] = json.loads(
                        c_dict.pop("citation_ids_json", "[]")
                    )
                except (json.JSONDecodeError, TypeError):
                    c_dict["citation_ids"] = []

                for k in ["numeric_check", "period_check", "contradiction_check"]:
                    raw = c_dict.pop(f"{k}_json", None)
                    if raw:
                        try:
                            c_dict[k] = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            c_dict[k] = None
                    else:
                        c_dict[k] = None

                c_dict["warnings"] = []
                claim_results.append(c_dict)

            run_dict["claim_results"] = claim_results
            run_dict["contradictions"] = [
                cr["contradiction_check"]
                for cr in claim_results
                if cr.get("contradiction_check")
                and cr["contradiction_check"].get("has_contradiction")
            ]
            run_dict["numeric_mismatches"] = [
                cr["numeric_check"]
                for cr in claim_results
                if cr.get("numeric_check") and not cr["numeric_check"].get("matched")
            ]
            run_dict["period_mismatches"] = [
                cr["period_check"]
                for cr in claim_results
                if cr.get("period_check")
                and not cr["period_check"].get("is_consistent")
            ]

            return run_dict

    def get_latest_verification_for_answer(
        self, answer_id: str
    ) -> dict[str, Any] | None:
        """Fetch the most recent verification run for a given answer_id."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT run_id FROM verification_runs WHERE answer_id = ? ORDER BY verified_at DESC LIMIT 1;",
                (answer_id.strip(),),
            ).fetchone()
            if not row:
                return None
            return self.get_verification_run(row["run_id"])

    # =========================================================================
    # Session 10: Multi-Agent Workflow & Execution Event Persistence
    # =========================================================================

    def save_workflow_run(self, data: dict[str, Any]) -> None:
        """Upsert a multi-agent workflow execution record."""
        now_iso = datetime.now(UTC).isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_workflows (
                    request_id, user_question, company_ticker, intent, workflow_type,
                    status, final_answer, verification_status, retrieved_evidence_count,
                    calculation_receipts_count, total_duration_ms, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    user_question = excluded.user_question,
                    company_ticker = excluded.company_ticker,
                    intent = excluded.intent,
                    workflow_type = excluded.workflow_type,
                    status = excluded.status,
                    final_answer = excluded.final_answer,
                    verification_status = excluded.verification_status,
                    retrieved_evidence_count = excluded.retrieved_evidence_count,
                    calculation_receipts_count = excluded.calculation_receipts_count,
                    total_duration_ms = excluded.total_duration_ms,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at;
                """,
                (
                    data["request_id"],
                    data["user_question"],
                    data.get("company_ticker"),
                    data.get("intent", "GENERAL_RESEARCH"),
                    data.get("workflow_type", "default"),
                    data.get("status", "PENDING"),
                    data.get("final_answer"),
                    data.get("verification_status"),
                    data.get("retrieved_evidence_count", 0),
                    data.get("calculation_receipts_count", 0),
                    data.get("total_duration_ms", 0.0),
                    data.get("error_message"),
                    data.get("created_at", now_iso),
                    data.get("updated_at", now_iso),
                ),
            )

    def get_workflow_run(self, request_id: str) -> dict[str, Any] | None:
        """Retrieve a workflow execution record and all its associated events."""
        with self.connection() as conn:
            wf_row = conn.execute(
                "SELECT * FROM agent_workflows WHERE request_id = ?;",
                (request_id.strip(),),
            ).fetchone()
            if not wf_row:
                return None
            wf_dict = dict(wf_row)
            events = self.list_execution_events(request_id)
            wf_dict["trace_events"] = events
            return wf_dict

    def list_recent_workflows(self, limit: int = 20) -> list[dict[str, Any]]:
        """List the most recent workflow runs."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_workflows ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_execution_event(self, event_data: dict[str, Any]) -> None:
        """Insert an agent execution step event."""
        metadata = event_data.get("metadata") or {}
        meta_json = (
            json.dumps(metadata) if isinstance(metadata, dict) else str(metadata)
        )

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_execution_events (
                    event_id, request_id, step_index, agent_name, node_name,
                    status, start_time, end_time, duration_ms,
                    input_summary, output_summary, error_message, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status = excluded.status,
                    end_time = excluded.end_time,
                    duration_ms = excluded.duration_ms,
                    output_summary = excluded.output_summary,
                    error_message = excluded.error_message,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    event_data["event_id"],
                    event_data["request_id"],
                    event_data.get("step_index", 0),
                    event_data.get("agent_name", "UnknownAgent"),
                    event_data.get("node_name", "unknown_node"),
                    event_data.get("status", "SUCCESS"),
                    event_data.get("start_time", datetime.now(UTC).isoformat()),
                    event_data.get("end_time", datetime.now(UTC).isoformat()),
                    event_data.get("duration_ms", 0.0),
                    event_data.get("input_summary"),
                    event_data.get("output_summary"),
                    event_data.get("error_message"),
                    meta_json,
                ),
            )

    def list_execution_events(self, request_id: str) -> list[dict[str, Any]]:
        """List all execution step events for a specific workflow run in order."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_execution_events
                WHERE request_id = ?
                ORDER BY step_index ASC, start_time ASC;
                """,
                (request_id.strip(),),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if "metadata_json" in d and d["metadata_json"]:
                    try:
                        d["metadata"] = json.loads(d["metadata_json"])
                    except Exception:
                        d["metadata"] = {}
                else:
                    d["metadata"] = {}
                result.append(d)
            return result
