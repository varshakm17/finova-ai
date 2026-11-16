"""Finova AI — Deployment Smoke Test & Readiness Acceptance Suite.

Performs non-destructive, environment-aware validation with explicit readiness states:
- READY: All mandatory deployment acceptance checks have passed without warnings.
- DEGRADED: Core deployment checks passed, but non-critical warnings remain.
- NOT_VERIFIED: Mandatory deployment acceptance could not be completed (e.g. Docker unavailable).
- BLOCKED: One or more mandatory deployment acceptance checks failed.

Guarantees 100% isolation: Never modifies or pollutes the user's configured SQLite database.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.data.sec_client import is_placeholder_user_agent
from backend.data.storage import Database
from config.settings import BASE_DIR, Settings, get_settings
from evaluation.docker_acceptance import DockerAcceptanceRunner
from frontend.backend_client import check_backend_health, resolve_backend_endpoints


class ReadinessState(str, Enum):
    """Explicit deployment readiness classification."""

    READY = "READY"
    DEGRADED = "DEGRADED"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass
class CheckResult:
    """Individual deployment check outcome."""

    name: str
    category: str
    passed: bool
    status: str  # "PASS", "WARN", "FAIL", "SKIPPED"
    is_mandatory: bool = True
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentReport:
    """Aggregated deployment readiness scorecard."""

    timestamp: str
    mode: str
    readiness_state: ReadinessState
    exit_code: int
    total_checks: int
    passed_count: int
    warn_count: int
    failed_count: int
    skipped_count: int
    mandatory_passed: int
    mandatory_failed: int
    mandatory_skipped: int
    is_deployable: bool
    reasons_not_ready: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    summary_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "mode": self.mode,
            "readiness_state": self.readiness_state.value,
            "exit_code": self.exit_code,
            "total_checks": self.total_checks,
            "passed_count": self.passed_count,
            "warn_count": self.warn_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "mandatory_passed": self.mandatory_passed,
            "mandatory_failed": self.mandatory_failed,
            "mandatory_skipped": self.mandatory_skipped,
            "is_deployable": self.is_deployable,
            "reasons_not_ready": self.reasons_not_ready,
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "status": c.status,
                    "is_mandatory": c.is_mandatory,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.checks
            ],
            "summary_notes": self.summary_notes,
        }


class DeploymentSmokeTester:
    """Orchestrates comprehensive deployment readiness smoke tests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run_static_checks(self) -> list[CheckResult]:
        """Validate configuration files and environment definitions."""
        results: list[CheckResult] = []

        # 1. Pydantic Settings Loading
        try:
            cfg = self.settings
            results.append(
                CheckResult(
                    name="settings_schema_validation",
                    category="static_config",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="Pydantic Settings loaded successfully from environment and defaults.",
                    details={
                        "app_name": cfg.APP_NAME,
                        "env": cfg.APP_ENV,
                        "port": cfg.PORT,
                    },
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="settings_schema_validation",
                    category="static_config",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"Settings initialization failed: {exc}",
                )
            )
            return results

        # 2. CORS Configuration Check
        cors_origins = cfg.get_cors_origins()
        has_wildcard = "*" in cors_origins
        if has_wildcard and cfg.CORS_ALLOW_CREDENTIALS:
            results.append(
                CheckResult(
                    name="cors_security_policy",
                    category="static_config",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message="Insecure CORS policy: Wildcard '*' cannot be combined with allow_credentials=True.",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="cors_security_policy",
                    category="static_config",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="CORS origin security policy validated successfully.",
                    details={"origins": cors_origins},
                )
            )

        # 3. SEC User-Agent Configuration Check
        ua = cfg.SEC_USER_AGENT
        if not ua or not ua.strip():
            results.append(
                CheckResult(
                    name="sec_user_agent_format",
                    category="static_config",
                    passed=True,
                    status="WARN",
                    is_mandatory=False,
                    message="SEC_USER_AGENT is not configured. Live SEC EDGAR operations will be blocked until configured in .env.",
                )
            )
        elif is_placeholder_user_agent(ua):
            results.append(
                CheckResult(
                    name="sec_user_agent_format",
                    category="static_config",
                    passed=True,
                    status="WARN",
                    is_mandatory=False,
                    message=f"SEC_USER_AGENT contains placeholder '{cfg.mask_sec_user_agent()}'. Live SEC requests require genuine identity in .env.",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="sec_user_agent_format",
                    category="static_config",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message=f"SEC User-Agent declared and valid: {cfg.mask_sec_user_agent()}",
                )
            )

        # 4. Critical Deployment File Presence Checks
        required_files = [
            ("requirements.txt", BASE_DIR / "requirements.txt", True),
            ("requirements.lock", BASE_DIR / "requirements.lock", True),
            ("Dockerfile.backend", BASE_DIR / "Dockerfile.backend", True),
            ("Dockerfile.frontend", BASE_DIR / "Dockerfile.frontend", True),
            ("docker-compose.yml", BASE_DIR / "docker-compose.yml", True),
            (".dockerignore", BASE_DIR / ".dockerignore", True),
            (".env.docker.example", BASE_DIR / ".env.docker.example", True),
        ]

        for fname, fpath, is_mand in required_files:
            if fpath.exists() and fpath.stat().st_size > 0:
                results.append(
                    CheckResult(
                        name=f"file_presence_{fname.replace('.', '_')}",
                        category="static_config",
                        passed=True,
                        status="PASS",
                        is_mandatory=is_mand,
                        message=f"Required deployment configuration present: {fname}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"file_presence_{fname.replace('.', '_')}",
                        category="static_config",
                        passed=False,
                        status="FAIL",
                        is_mandatory=is_mand,
                        message=f"Missing or empty required deployment file: {fname}",
                    )
                )

        return results

    def run_local_runtime_checks(self) -> list[CheckResult]:
        """Validate local database persistence, filesystem storage, and connectivity without touching production DB."""
        results: list[CheckResult] = []

        # 1. Database Connection & Schema Setup (ISOLATED TEMPORARY DATABASE)
        try:
            with tempfile.TemporaryDirectory(prefix="finova_diag_db_") as tmp_dir:
                tmp_db_file = Path(tmp_dir) / "diag_finova.db"
                # Initialize isolated diagnostic database
                diag_db = Database(str(tmp_db_file))
                diag_db.init_db()

                with diag_db.connection() as conn:
                    cur = conn.cursor()
                    tables = [
                        row[0]
                        for row in cur.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    ]
                    journal_mode = cur.execute("PRAGMA journal_mode;").fetchone()[0]
                    fk_mode = cur.execute("PRAGMA foreign_keys;").fetchone()[0]

                results.append(
                    CheckResult(
                        name="database_schema_and_wal",
                        category="local_runtime",
                        passed=True,
                        status="PASS",
                        is_mandatory=True,
                        message=f"Diagnostic database initialized cleanly with {len(tables)} tables (journal: {journal_mode}, foreign_keys: {fk_mode}). Real database untouched.",
                        details={
                            "tables_count": len(tables),
                            "journal_mode": journal_mode,
                            "foreign_keys": fk_mode,
                        },
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="database_schema_and_wal",
                    category="local_runtime",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"Database schema initialization failed: {exc}",
                )
            )

        # 2. Database Write-Read-Rollback Transaction Resilience (ISOLATED TEMPORARY DATABASE)
        try:
            with tempfile.TemporaryDirectory(prefix="finova_diag_tx_") as tmp:
                temp_db_path = str(Path(tmp) / "persist_test.db")
                db_test = Database(temp_db_path)
                db_test.init_db()

                # Insert probe record
                with db_test.connection() as conn:
                    conn.execute(
                        "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                        (
                            "0000000001",
                            "TEST_CO",
                            "Test Company Persistence",
                            "2026-01-01T00:00:00Z",
                        ),
                    )

                # Reopen connection and verify persistence
                with db_test.connection() as conn:
                    found = conn.execute(
                        "SELECT name FROM companies WHERE ticker = ?", ("TEST_CO",)
                    ).fetchone()
                    assert found is not None and found[0] == "Test Company Persistence"

                # Verify transaction rollback on failure
                try:
                    with db_test.connection() as conn:
                        conn.execute(
                            "INSERT INTO companies (cik, ticker, name, updated_at) VALUES (?, ?, ?, ?)",
                            (
                                "0000000002",
                                "FAIL_CO",
                                "Should Rollback",
                                "2026-01-01T00:00:00Z",
                            ),
                        )
                        raise RuntimeError("Simulated failure inside transaction")
                except RuntimeError:
                    pass

                with db_test.connection() as conn:
                    check_fail = conn.execute(
                        "SELECT ticker FROM companies WHERE ticker = ?", ("FAIL_CO",)
                    ).fetchone()
                    assert check_fail is None, (
                        "Rollback failed: record was committed despite exception"
                    )

            results.append(
                CheckResult(
                    name="database_persistence_and_rollback",
                    category="local_runtime",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="SQLite persistent read, write, and rollback verified cleanly on isolated database.",
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="database_persistence_and_rollback",
                    category="local_runtime",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"Database persistence or rollback check failed: {exc}",
                )
            )

        # 3. Frontend-Backend URL Resolver Check
        try:
            endpoints = resolve_backend_endpoints(settings=self.settings)
            assert not endpoints.api_v1_url.endswith("/")
            results.append(
                CheckResult(
                    name="frontend_url_resolution",
                    category="local_runtime",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message=f"Frontend resolved endpoints: base='{endpoints.base_url}', api_v1='{endpoints.api_v1_url}'.",
                    details={
                        "base_url": endpoints.base_url,
                        "api_v1_url": endpoints.api_v1_url,
                        "source": endpoints.configured_from,
                    },
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="frontend_url_resolution",
                    category="local_runtime",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"Frontend backend URL resolution failed: {exc}",
                )
            )

        # 4. Storage Directory Permissions
        dirs_to_check = [
            ("datasets/filings", BASE_DIR / "datasets" / "filings"),
            ("datasets/indexes", BASE_DIR / "datasets" / "indexes"),
            ("logs", BASE_DIR / "logs"),
            ("reports/demos", BASE_DIR / "reports" / "demos"),
        ]

        for dname, dpath in dirs_to_check:
            try:
                dpath.mkdir(parents=True, exist_ok=True)
                probe_file = dpath / ".write_probe"
                probe_file.write_text("probe", encoding="utf-8")
                probe_file.unlink()
                results.append(
                    CheckResult(
                        name=f"directory_writable_{dname.replace('/', '_')}",
                        category="local_runtime",
                        passed=True,
                        status="PASS",
                        is_mandatory=True,
                        message=f"Storage directory writable: {dname}",
                    )
                )
            except Exception as exc:
                results.append(
                    CheckResult(
                        name=f"directory_writable_{dname.replace('/', '_')}",
                        category="local_runtime",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"Storage directory '{dname}' not writable: {exc}",
                    )
                )

        # 5. Live Backend Connectivity (Optional during offline smoke testing)
        try:
            endpoints = resolve_backend_endpoints(settings=self.settings)
            is_online, health_data, health_err = check_backend_health(
                endpoints, timeout=1.0
            )
            if is_online and health_data:
                results.append(
                    CheckResult(
                        name="backend_http_health",
                        category="local_runtime",
                        passed=True,
                        status="PASS",
                        is_mandatory=False,
                        message=f"Backend HTTP health check succeeded (status: {health_data.get('status')}).",
                        details=health_data,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name="backend_http_health",
                        category="local_runtime",
                        passed=True,
                        status="WARN",
                        is_mandatory=False,
                        message=f"Backend is not currently running locally ({health_err or 'offline'}). Run 'uvicorn backend.main:app' to start.",
                    )
                )
        except Exception as exc:
            results.append(
                CheckResult(
                    name="backend_http_health",
                    category="local_runtime",
                    passed=True,
                    status="WARN",
                    is_mandatory=False,
                    message=f"Backend health check warning: {exc}",
                )
            )

        return results

    def run_docker_checks(self) -> list[CheckResult]:
        """Validate Docker deployment acceptance via DockerAcceptanceRunner."""
        runner = DockerAcceptanceRunner()
        docker_res = runner.run_acceptance_suite()
        results: list[CheckResult] = []

        for dr in docker_res:
            results.append(
                CheckResult(
                    name=dr.name,
                    category=dr.category,
                    passed=dr.passed,
                    status=dr.status,
                    is_mandatory=dr.is_mandatory,
                    message=dr.message,
                    details=dr.details,
                )
            )
        return results

    def evaluate_report(
        self, checks: list[CheckResult], mode: str = "all"
    ) -> DeploymentReport:
        """Evaluate readiness state machine and return structured deployment scorecard."""
        passed_c = sum(1 for c in checks if c.status == "PASS")
        warn_c = sum(1 for c in checks if c.status == "WARN")
        fail_c = sum(1 for c in checks if c.status == "FAIL")
        skip_c = sum(1 for c in checks if c.status == "SKIPPED")

        mand_passed = sum(1 for c in checks if c.is_mandatory and c.status == "PASS")
        mand_failed = sum(1 for c in checks if c.is_mandatory and c.status == "FAIL")
        mand_skipped = sum(
            1 for c in checks if c.is_mandatory and c.status == "SKIPPED"
        )

        reasons: list[str] = []

        # Determine explicit state machine outcome
        if mand_failed > 0 or fail_c > 0:
            state = ReadinessState.BLOCKED
            exit_code = 1
            for c in checks:
                if c.status == "FAIL":
                    reasons.append(f"Mandatory check '{c.name}' failed: {c.message}")
        elif mand_skipped > 0:
            state = ReadinessState.NOT_VERIFIED
            exit_code = 2
            for c in checks:
                if c.is_mandatory and c.status == "SKIPPED":
                    reasons.append(
                        f"Mandatory acceptance check '{c.name}' was skipped: {c.message}"
                    )
        elif warn_c > 0:
            state = ReadinessState.DEGRADED
            exit_code = 0
            for c in checks:
                if c.status == "WARN":
                    reasons.append(f"Non-critical warning '{c.name}': {c.message}")
        else:
            state = ReadinessState.READY
            exit_code = 0

        is_deployable = state in (ReadinessState.READY, ReadinessState.DEGRADED)

        notes = [
            f"Deployment acceptance evaluation completed in mode '{mode}'.",
            f"Evaluated {len(checks)} system checks ({passed_c} PASS, {warn_c} WARN, {fail_c} FAIL, {skip_c} SKIPPED).",
            f"Readiness State: {state.value} (exit code: {exit_code}).",
        ]
        if reasons:
            notes.append(f"Readiness notes: {'; '.join(reasons[:3])}")

        return DeploymentReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            mode=mode,
            readiness_state=state,
            exit_code=exit_code,
            total_checks=len(checks),
            passed_count=passed_c,
            warn_count=warn_c,
            failed_count=fail_c,
            skipped_count=skip_c,
            mandatory_passed=mand_passed,
            mandatory_failed=mand_failed,
            mandatory_skipped=mand_skipped,
            is_deployable=is_deployable,
            reasons_not_ready=reasons,
            checks=checks,
            summary_notes=notes,
        )

    # Alias for internal or test backwards compatibility
    _evaluate_report = evaluate_report

    def run_all(self, mode: str = "all") -> DeploymentReport:
        """Execute selected deployment smoke tests and evaluate readiness state."""
        checks: list[CheckResult] = []

        if mode in ("static", "all"):
            checks.extend(self.run_static_checks())

        if mode in ("local", "all"):
            checks.extend(self.run_local_runtime_checks())

        if mode in ("docker", "all"):
            checks.extend(self.run_docker_checks())

        return self.evaluate_report(checks, mode=mode)


def main() -> None:
    """CLI runner for Deployment Smoke Tests."""
    parser = argparse.ArgumentParser(description="Finova AI Deployment Smoke Tester")
    parser.add_argument(
        "--mode",
        choices=["all", "static", "local", "docker"],
        default="all",
        help="Scope of deployment smoke tests (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results",
    )
    args = parser.parse_args()

    tester = DeploymentSmokeTester()
    report = tester.run_all(mode=args.mode)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print("\n" + "=" * 78)
        print("  FINOVA AI SYSTEM DEPLOYMENT ACCEPTANCE SCORECARD")
        print("=" * 78)
        print(f"  Execution Mode:       {report.mode.upper()}")
        print(
            f"  Total Checks:         {report.total_checks} "
            f"({report.passed_count} PASS, {report.warn_count} WARN, {report.failed_count} FAIL, {report.skipped_count} SKIPPED)"
        )
        print(f"  Readiness State:      {report.readiness_state.value}")
        print(
            f"  Deployable Outcome:   {'DEPLOYABLE' if report.is_deployable else 'NOT DEPLOYABLE'}"
        )
        print(f"  Process Exit Code:    {report.exit_code}")
        print("-" * 78)
        print(
            f"  {'Status':<8} | {'Category':<18} | {'Check Name':<35} | {'Mandatory'}"
        )
        print("-" * 78)
        for c in report.checks:
            badge = f"[{c.status}]"
            mand_badge = "YES" if c.is_mandatory else "NO"
            print(f"  {badge:<8} | {c.category:<18} | {c.name:<35} | {mand_badge}")
            if c.status in ("WARN", "FAIL", "SKIPPED"):
                print(f"           - {c.message}")
        print("=" * 78)
        for n in report.summary_notes:
            print(f"  * {n}")
        if report.reasons_not_ready:
            print("\n  Readiness Explanations:")
            for r in report.reasons_not_ready:
                print(f"    - {r}")
        print("=" * 78 + "\n")

    sys.exit(report.exit_code)


if __name__ == "__main__":
    main()
