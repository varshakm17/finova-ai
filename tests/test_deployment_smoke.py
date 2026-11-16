"""Tests for deployment smoke test suite and readiness state machine."""

from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from evaluation.deployment_smoke_tests import (
    CheckResult,
    DeploymentSmokeTester,
    ReadinessState,
)


def test_deployment_smoke_tester_static_mode() -> None:
    """Verify static checks inspect settings, CORS, and container files."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="static")

    assert report.mode == "static"
    assert report.total_checks >= 7
    assert report.failed_count == 0
    assert report.readiness_state in (ReadinessState.READY, ReadinessState.DEGRADED)
    assert report.is_deployable is True
    assert report.exit_code == 0


def test_deployment_smoke_tester_local_mode() -> None:
    """Verify local runtime checks inspect database schema, persistence, and directories."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="local")

    assert report.mode == "local"
    assert report.total_checks >= 5
    assert report.failed_count == 0
    assert report.readiness_state in (ReadinessState.READY, ReadinessState.DEGRADED)
    assert report.is_deployable is True
    assert report.exit_code == 0


def test_deployment_smoke_tester_docker_mode() -> None:
    """Verify docker checks accurately report SKIPPED & NOT_VERIFIED if docker is unavailable on host."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="docker")

    assert report.mode == "docker"
    assert len(report.checks) >= 1
    # On this host without Docker CLI, it reports SKIPPED & NOT_VERIFIED
    if report.checks[0].status == "SKIPPED":
        assert report.readiness_state == ReadinessState.NOT_VERIFIED
        assert report.exit_code == 2
        assert report.is_deployable is False
        assert len(report.reasons_not_ready) >= 1


def test_readiness_state_machine_combinations() -> None:
    """Verify state machine transitions across READY, DEGRADED, NOT_VERIFIED, and BLOCKED."""
    tester = DeploymentSmokeTester()

    # 1. READY (all mandatory pass, 0 warned, 0 failed, 0 skipped)
    checks_ready = [
        CheckResult("c1", "cat", True, "PASS", is_mandatory=True),
        CheckResult("c2", "cat", True, "PASS", is_mandatory=False),
    ]
    rep_ready = tester._evaluate_report(checks_ready, mode="test")
    assert rep_ready.readiness_state == ReadinessState.READY
    assert rep_ready.exit_code == 0
    assert rep_ready.is_deployable is True

    # 2. DEGRADED (mandatory pass, optional warned)
    checks_degraded = [
        CheckResult("c1", "cat", True, "PASS", is_mandatory=True),
        CheckResult(
            "c2", "cat", True, "WARN", is_mandatory=False, message="Low memory warning"
        ),
    ]
    rep_degraded = tester._evaluate_report(checks_degraded, mode="test")
    assert rep_degraded.readiness_state == ReadinessState.DEGRADED
    assert rep_degraded.exit_code == 0
    assert rep_degraded.is_deployable is True
    assert len(rep_degraded.reasons_not_ready) == 1

    # 3. NOT_VERIFIED (mandatory skipped)
    checks_not_verified = [
        CheckResult("c1", "cat", True, "PASS", is_mandatory=True),
        CheckResult(
            "c2", "cat", False, "SKIPPED", is_mandatory=True, message="Docker missing"
        ),
    ]
    rep_not_verified = tester._evaluate_report(checks_not_verified, mode="test")
    assert rep_not_verified.readiness_state == ReadinessState.NOT_VERIFIED
    assert rep_not_verified.exit_code == 2
    assert rep_not_verified.is_deployable is False
    assert len(rep_not_verified.reasons_not_ready) == 1

    # 4. BLOCKED (mandatory failed)
    checks_blocked = [
        CheckResult(
            "c1", "cat", False, "FAIL", is_mandatory=True, message="Port bind collision"
        ),
        CheckResult("c2", "cat", True, "PASS", is_mandatory=True),
    ]
    rep_blocked = tester._evaluate_report(checks_blocked, mode="test")
    assert rep_blocked.readiness_state == ReadinessState.BLOCKED
    assert rep_blocked.exit_code == 1
    assert rep_blocked.is_deployable is False
    assert len(rep_blocked.reasons_not_ready) == 1


def test_diagnostics_never_modifies_configured_database(tmp_path: Path) -> None:
    """Regression test: running local runtime diagnostics must not touch or alter the user's real DB."""
    # Create an initial user database with known content
    user_db_file = tmp_path / "actual_user_app.db"
    import sqlite3

    conn = sqlite3.connect(str(user_db_file))
    conn.execute("CREATE TABLE user_sentinel (key TEXT, val TEXT);")
    conn.execute("INSERT INTO user_sentinel VALUES ('initial_key', 'initial_val');")
    conn.commit()
    conn.close()

    initial_size = user_db_file.stat().st_size
    initial_mtime = user_db_file.stat().st_mtime_ns

    # Configure tester with this database path
    test_settings = Settings(DATABASE_URL=f"sqlite:///{user_db_file.as_posix()}")
    tester = DeploymentSmokeTester(settings=test_settings)

    # Run local runtime checks
    report = tester.run_all(mode="local")
    assert report.failed_count == 0

    # Verify that actual_user_app.db has NOT been touched or modified
    assert user_db_file.exists()
    conn_after = sqlite3.connect(str(user_db_file))
    cur = conn_after.cursor()
    tables = [
        row[0]
        for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    conn_after.close()

    # The actual user database should only have user_sentinel table, never application tables
    assert tables == ["user_sentinel"]
    assert user_db_file.stat().st_size == initial_size
    assert user_db_file.stat().st_mtime_ns == initial_mtime
