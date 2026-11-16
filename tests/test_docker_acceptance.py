"""Tests for Docker deployment acceptance runner and configuration integrity."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import yaml

from evaluation.docker_acceptance import (
    PROJECT_ROOT,
    DockerAcceptanceRunner,
    validate_host_ports,
)


def test_docker_compose_configurable_host_ports() -> None:
    """Verify docker-compose.yml uses configurable host ports for backend and frontend."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "backend" in services, "backend service must be defined"
    assert "frontend" in services, "frontend service must be defined"

    backend_ports = services["backend"].get("ports", [])
    frontend_ports = services["frontend"].get("ports", [])

    assert any("${PORT:-8000}:8000" in str(p) for p in backend_ports), (
        f"Backend must map configurable host PORT to internal 8000, got: {backend_ports}"
    )
    assert any("${FRONTEND_PORT:-8501}:8501" in str(p) for p in frontend_ports), (
        f"Frontend must map configurable host FRONTEND_PORT to internal 8501, got: {frontend_ports}"
    )


def test_docker_compose_no_fixed_container_names() -> None:
    """Verify docker-compose.yml does not declare fixed container_name, ensuring project isolation."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "container_name" not in services.get("backend", {}), (
        "backend must not have fixed container_name"
    )
    assert "container_name" not in services.get("frontend", {}), (
        "frontend must not have fixed container_name"
    )


def test_docker_acceptance_runner_unique_project_ids() -> None:
    """Verify each runner generates a distinct UUID-based project identifier."""
    runner1 = DockerAcceptanceRunner()
    runner2 = DockerAcceptanceRunner()

    assert runner1.project_name.startswith("finova-acc-")
    assert runner2.project_name.startswith("finova-acc-")
    assert runner1.project_name != runner2.project_name


def test_validate_host_ports_valid() -> None:
    """Verify valid available host ports pass validation."""
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = (
            1  # 1 means port is free (connection refused)
        )
        mock_sock_cls.return_value.__enter__.return_value = mock_sock

        valid, msg = validate_host_ports(18000, 18501)
        assert valid is True
        assert "valid and available" in msg


def test_validate_host_ports_invalid_range() -> None:
    """Verify ports outside 1..65535 fail validation with clear error message."""
    valid1, msg1 = validate_host_ports(0, 18501)
    assert valid1 is False
    assert "Invalid backend host port 0" in msg1

    valid2, msg2 = validate_host_ports(18000, 70000)
    assert valid2 is False
    assert "Invalid frontend host port 70000" in msg2


def test_validate_host_ports_collision() -> None:
    """Verify identical backend and frontend ports fail collision validation."""
    valid, msg = validate_host_ports(18000, 18000)
    assert valid is False
    assert "Port collision" in msg


def test_validate_host_ports_occupied() -> None:
    """Verify occupied ports are detected and reported clearly."""
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0  # 0 means port is currently in use
        mock_sock_cls.return_value.__enter__.return_value = mock_sock

        valid, msg = validate_host_ports(18000, 18501)
        assert valid is False
        assert "already in use" in msg


def test_runner_docker_cli_missing() -> None:
    """Verify runner reports SKIPPED when Docker CLI is not present."""
    runner = DockerAcceptanceRunner()
    runner.docker_cli = None

    results = runner.run_acceptance_suite()
    assert len(results) == 1
    assert results[0].name == "docker_cli_availability"
    assert results[0].status == "SKIPPED"
    assert results[0].passed is False
    assert "Docker CLI is not installed" in results[0].message


def test_runner_docker_daemon_connectivity_failure() -> None:
    """Verify runner reports SKIPPED when Docker daemon is not responding."""
    runner = DockerAcceptanceRunner()
    runner.docker_cli = "/usr/bin/docker"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=1,
            stdout="",
            stderr="Cannot connect to the Docker daemon",
        )

        results = runner.run_acceptance_suite()
        assert len(results) == 2
        assert results[0].status == "PASS"
        assert results[1].name == "docker_daemon_connectivity"
        assert results[1].status == "SKIPPED"
        assert results[1].passed is False
        assert "daemon is not running" in results[1].message


def test_runner_docker_daemon_timeout() -> None:
    """Verify runner handles Docker daemon timeout cleanly as SKIPPED without uncaught exception."""
    runner = DockerAcceptanceRunner()
    runner.docker_cli = "/usr/bin/docker"

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["docker", "info"], timeout=8
        )

        results = runner.run_acceptance_suite()
        assert len(results) == 2
        assert results[1].name == "docker_daemon_connectivity"
        assert results[1].status == "SKIPPED"
        assert "timed out after 8s" in results[1].message


def test_non_root_validation_success() -> None:
    """Verify non-root check passes for unprivileged UID (1000 appuser)."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "1000\n", "", None)

        res = runner._validate_non_root("backend")
        assert res.name == "docker_backend_non_root_execution"
        assert res.passed is True
        assert res.status == "PASS"
        assert res.details.get("uid") == 1000


def test_non_root_validation_root_violation() -> None:
    """Verify non-root check fails if container runs as root (UID 0)."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "0\n", "", None)

        res = runner._validate_non_root("backend")
        assert res.passed is False
        assert res.status == "FAIL"
        assert "Security violation" in res.message
        assert res.details.get("uid") == 0


def test_non_root_validation_command_failure() -> None:
    """Verify non-root check fails if the id command returns non-zero exit code."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (1, "", "exec failed: container not running", None)

        res = runner._validate_non_root("backend")
        assert res.passed is False
        assert res.status == "FAIL"
        assert "non-zero exit code" in res.message


def test_non_root_validation_invalid_output() -> None:
    """Verify non-root check fails if id output is empty or non-numeric."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "not_a_uid", "", None)

        res = runner._validate_non_root("frontend")
        assert res.passed is False
        assert res.status == "FAIL"
        assert "did not return a valid numeric UID" in res.message

    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "", "", None)

        res = runner._validate_non_root("frontend")
        assert res.passed is False
        assert res.status == "FAIL"


def test_frontend_backend_connectivity_success() -> None:
    """Verify internal network connectivity check passes on CONNECTIVITY_OK."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (
            0,
            "CONNECTIVITY_OK:http://backend:8000/api/v1\n",
            "",
            None,
        )

        res = runner._check_frontend_backend_connectivity()
        assert res.name == "docker_frontend_backend_connectivity"
        assert res.passed is True
        assert res.status == "PASS"


def test_frontend_backend_connectivity_failure() -> None:
    """Verify internal network connectivity check fails when probe returns error."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (
            1,
            "",
            "Connection refused: http://backend:8000/api/v1/health",
            None,
        )

        res = runner._check_frontend_backend_connectivity()
        assert res.passed is False
        assert res.status == "FAIL"
        assert "could not communicate" in res.message


def test_persistence_write_failure() -> None:
    """Verify persistence check fails when initial SQLite write fails."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (1, "", "database is locked", None)

        res = runner._check_persistence()
        assert res.passed is False
        assert res.status == "FAIL"
        assert res.details.get("step") == "write_marker"


def test_persistence_restart_failure() -> None:
    """Verify persistence check fails when backend restart command fails."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        # First call: write marker succeeds; second call: restart fails
        mock_cmd.side_effect = [
            (0, "WRITE_OK\n", "", None),
            (1, "", "container restart failed", None),
        ]

        res = runner._check_persistence()
        assert res.passed is False
        assert res.status == "FAIL"
        assert res.details.get("step") == "restart_backend"


def test_persistence_read_failure() -> None:
    """Verify persistence check fails when post-restart read command fails."""
    runner = DockerAcceptanceRunner()
    with (
        patch.object(runner, "_run_compose_cmd") as mock_cmd,
        patch("httpx.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=200)
        mock_cmd.side_effect = [
            (0, "WRITE_OK\n", "", None),  # write
            (0, "", "", None),  # restart
            (1, "", "table not found", None),  # read fails
        ]

        res = runner._check_persistence()
        assert res.passed is False
        assert res.status == "FAIL"
        assert res.details.get("step") == "read_marker"


def test_persistence_mismatch_failure() -> None:
    """Verify persistence check fails when marker value does not match exactly."""
    runner = DockerAcceptanceRunner()
    with (
        patch.object(runner, "_run_compose_cmd") as mock_cmd,
        patch("httpx.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=200)
        mock_cmd.side_effect = [
            (0, "WRITE_OK\n", "", None),  # write
            (0, "", "", None),  # restart
            (0, "different_marker\n", "", None),  # read mismatch
        ]

        res = runner._check_persistence()
        assert res.passed is False
        assert res.status == "FAIL"
        assert res.details.get("step") == "verify_marker"


def test_persistence_success() -> None:
    """Verify persistence check passes when unique marker is written and read back."""
    runner = DockerAcceptanceRunner()
    with (
        patch.object(runner, "_run_compose_cmd") as mock_cmd,
        patch("httpx.get") as mock_http,
    ):
        mock_http.return_value = MagicMock(status_code=200)

        recorded_marker: list[str] = []

        def side_effect_cmd(args, **kwargs):
            import re

            cmd_str = " ".join(str(a) for a in args)
            if "CREATE TABLE" in cmd_str:
                match = re.search(r"acc_persist_[a-f0-9]+", cmd_str)
                if match:
                    recorded_marker.append(match.group(0))
                return 0, "WRITE_OK\n", "", None
            if "restart" in args:
                return 0, "", "", None
            if "SELECT val" in cmd_str:
                val = recorded_marker[0] if recorded_marker else "test_val"
                return 0, f"{val}\n", "", None
            return 0, "", "", None

        mock_cmd.side_effect = side_effect_cmd

        res = runner._check_persistence()
        assert res.passed is True
        assert res.status == "PASS"
        assert "persistence verified" in res.message


def test_subprocess_timeout_handling() -> None:
    """Verify _run_compose_cmd captures TimeoutExpired cleanly without unhandled exceptions."""
    runner = DockerAcceptanceRunner()
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["docker", "compose"], timeout=5
        )

        code, stdout, stderr, err = runner._run_compose_cmd(["ps"], timeout=5)
        assert code == -1
        assert err is not None
        assert "timed out after 5s" in err


def test_safe_project_scoped_cleanup_no_prune() -> None:
    """Verify acceptance runner only runs project-scoped down -v and never global prune."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-testproject")
    runner.docker_cli = "/usr/bin/docker"

    with patch.object(runner, "_run_compose_cmd") as mock_compose:
        mock_compose.return_value = (0, "", "", None)

        # Trigger cleanup via _run_compose_cmd directly
        down_code, _, _, err = runner._run_compose_cmd(["down", "-v"], timeout=30)
        assert down_code == 0
        assert err is None

        # Verify command sent to compose has -p finova-acc-testproject
        calls = mock_compose.call_args_list
        assert len(calls) >= 1
        args_passed = calls[0][0][0]
        assert "down" in args_passed
        assert "-v" in args_passed

    # Verify source code of docker_acceptance.py does NOT contain destructive commands
    src_file = PROJECT_ROOT / "evaluation" / "docker_acceptance.py"
    content = src_file.read_text(encoding="utf-8")
    assert "system prune" not in content
    assert "image prune" not in content
    assert "volume prune" not in content


def test_non_root_validation_frontend_both_outcomes() -> None:
    """Verify frontend non-root check correctly distinguishes non-root appuser vs root."""
    runner = DockerAcceptanceRunner()
    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "1000\n", "", None)
        pass_res = runner._validate_non_root("frontend")
        assert pass_res.name == "docker_frontend_non_root_execution"
        assert pass_res.passed is True
        assert pass_res.status == "PASS"

    with patch.object(runner, "_run_compose_cmd") as mock_cmd:
        mock_cmd.return_value = (0, "0\n", "", None)
        fail_res = runner._validate_non_root("frontend")
        assert fail_res.passed is False
        assert fail_res.status == "FAIL"
        assert "Security violation" in fail_res.message


def test_full_mocked_acceptance_suite_success() -> None:
    """Verify full end-to-end acceptance suite passes cleanly when all services and checks succeed."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-fulltest")
    runner.docker_cli = "/usr/bin/docker"

    with (
        patch("subprocess.run") as mock_sub,
        patch.object(runner, "_run_compose_cmd") as mock_compose,
        patch(
            "evaluation.docker_acceptance.validate_host_ports",
            return_value=(True, "Ports available"),
        ),
        patch("httpx.get") as mock_http,
    ):
        mock_sub.return_value = subprocess.CompletedProcess(
            args=["docker", "info"],
            returncode=0,
            stdout="Server Version: 24.0.5\n",
            stderr="",
        )
        mock_http.return_value = MagicMock(
            status_code=200, json=lambda: {"status": "healthy"}
        )

        recorded_marker: list[str] = []

        def side_effect(args, **kwargs):
            cmd_str = " ".join(str(a) for a in args)
            if "config" in args:
                return 0, "name: finova-acc-fulltest", "", None
            if "build" in args:
                return 0, "built image", "", None
            if "up" in args:
                return 0, "started containers", "", None
            if "id" in args:
                return 0, "1000\n", "", None
            if "CONNECTIVITY_OK" in cmd_str:
                return 0, "CONNECTIVITY_OK:http://backend:8000/api/v1\n", "", None
            if "CREATE TABLE" in cmd_str:
                import re

                match = re.search(r"acc_persist_[a-f0-9]+", cmd_str)
                if match:
                    recorded_marker.append(match.group(0))
                return 0, "WRITE_OK\n", "", None
            if "restart" in args:
                return 0, "restarted", "", None
            if "SELECT val" in cmd_str:
                val = recorded_marker[0] if recorded_marker else "test_val"
                return 0, f"{val}\n", "", None
            if "down" in args:
                return 0, "removed", "", None
            return 0, "", "", None

        mock_compose.side_effect = side_effect

        results = runner.run_acceptance_suite()
        statuses = [r.status for r in results]
        names = [r.name for r in results]

        assert all(s == "PASS" for s in statuses), (
            f"Unexpected non-PASS statuses: {list(zip(names, statuses))}"
        )
        assert "docker_cli_availability" in names
        assert "docker_daemon_connectivity" in names
        assert "docker_host_port_validation" in names
        assert "docker_compose_config_validation" in names
        assert "docker_build_backend_image" in names
        assert "docker_build_frontend_image" in names
        assert "docker_container_startup" in names
        assert "docker_backend_health_check" in names
        assert "docker_frontend_health_check" in names
        assert "docker_backend_non_root_execution" in names
        assert "docker_frontend_non_root_execution" in names
        assert "docker_frontend_backend_connectivity" in names
        assert "docker_data_volume_persistence" in names
        assert "docker_environment_cleanup" in names


def test_full_mocked_acceptance_suite_frontend_health_failure() -> None:
    """Verify suite fails and cleans up if frontend health check fails."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-failtest")
    runner.docker_cli = "/usr/bin/docker"

    with (
        patch("subprocess.run") as mock_sub,
        patch.object(runner, "_run_compose_cmd") as mock_compose,
        patch(
            "evaluation.docker_acceptance.validate_host_ports",
            return_value=(True, "Ports available"),
        ),
        patch("httpx.get") as mock_http,
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0.0, 0.1, 0.2, 35.0, 36.0, 37.0]),
    ):
        mock_sub.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=0, stdout="", stderr=""
        )

        # Backend is healthy, frontend returns 500
        def fake_get(url, **kwargs):
            if "8000" in url or "backend" in url:
                return MagicMock(status_code=200, json=lambda: {"status": "healthy"})
            return MagicMock(status_code=500)

        mock_http.side_effect = fake_get
        mock_compose.return_value = (0, "", "", None)

        results = runner.run_acceptance_suite()
        names = [r.name for r in results]
        statuses = {r.name: r.status for r in results}

        assert "docker_frontend_health_check" in names
        assert statuses["docker_frontend_health_check"] == "FAIL"
        # Teardown must still be executed in finally
        assert "docker_environment_cleanup" in names


def test_cleanup_failure_reported_as_warning() -> None:
    """Verify cleanup failures in finally block are reported as WARN without crashing."""
    runner = DockerAcceptanceRunner()
    runner.docker_cli = "/usr/bin/docker"

    with (
        patch("subprocess.run") as mock_sub,
        patch.object(runner, "_run_compose_cmd") as mock_compose,
        patch(
            "evaluation.docker_acceptance.validate_host_ports",
            return_value=(True, "Ports available"),
        ),
    ):
        mock_sub.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=0, stdout="", stderr=""
        )

        def side_effect(args, **kwargs):
            if "up" in args:
                return 1, "", "startup failed", None
            if "down" in args:
                return 1, "", "failed to remove volume", None
            return 0, "", "", None

        mock_compose.side_effect = side_effect

        results = runner.run_acceptance_suite()
        cleanup_res = next(
            (r for r in results if r.name == "docker_environment_cleanup"), None
        )
        assert cleanup_res is not None
        assert cleanup_res.status == "WARN"
        assert cleanup_res.passed is False
