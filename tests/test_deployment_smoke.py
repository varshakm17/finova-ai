"""Tests for deployment smoke test suite."""

from __future__ import annotations

from evaluation.deployment_smoke_tests import DeploymentSmokeTester


def test_deployment_smoke_tester_static_mode() -> None:
    """Verify static checks inspect settings, CORS, and container files."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="static")

    assert report.mode == "static"
    assert report.total_checks >= 5
    assert report.failed_count == 0
    assert report.is_deployable is True


def test_deployment_smoke_tester_local_mode() -> None:
    """Verify local runtime checks inspect database schema, persistence, and directories."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="local")

    assert report.mode == "local"
    assert report.total_checks >= 4
    assert report.failed_count == 0
    assert report.is_deployable is True


def test_deployment_smoke_tester_docker_mode() -> None:
    """Verify docker checks accurately report SKIPPED if docker is unavailable on host."""
    tester = DeploymentSmokeTester()
    report = tester.run_all(mode="docker")

    assert report.mode == "docker"
    assert len(report.checks) >= 1
    # On this Windows host, Docker CLI is not installed, so it must be SKIPPED
    assert report.checks[0].status in ("SKIPPED", "PASS")
    assert report.failed_count == 0
