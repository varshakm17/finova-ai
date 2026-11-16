"""Tests for Docker deployment acceptance runner and configuration integrity."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from evaluation.docker_acceptance import (
    PROJECT_ROOT,
    DockerAcceptanceRunner,
    generate_frontend_connectivity_probe,
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


class DummyHTTPResponse:
    """Simulated urllib HTTP response for in-process probe testing."""

    def __init__(self, status: int, body: bytes):
        self._status = status
        self._body = body

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


def execute_probe_in_process(
    probe_code: str,
    env: dict[str, str],
    mock_urlopen_side_effect: Any = None,
    mock_response: Any = None,
) -> tuple[int, str, str, list[urllib.request.Request]]:
    """Execute the exact generated probe code in-process, capturing exit code, output, and outgoing requests."""
    captured_requests: list[urllib.request.Request] = []
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    def fake_urlopen(req: urllib.request.Request | str, timeout: float = 5):
        if isinstance(req, str):
            req = urllib.request.Request(req)
        captured_requests.append(req)
        if mock_urlopen_side_effect:
            if callable(mock_urlopen_side_effect):
                return mock_urlopen_side_effect(req, timeout=timeout)
            raise mock_urlopen_side_effect
        return mock_response

    with (
        patch.dict(os.environ, env, clear=True),
        patch("sys.stdout", stdout_buf),
        patch("sys.stderr", stderr_buf),
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        compiled = compile(probe_code, "<frontend_probe>", "exec")
        try:
            exec(compiled, {"__name__": "__main__"})
        except SystemExit as exc:
            exit_code = (
                exc.code
                if isinstance(exc.code, int)
                else (0 if exc.code is None else 1)
            )

    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue(), captured_requests


def test_probe_compiles_successfully() -> None:
    """Verify that generate_frontend_connectivity_probe() produces syntactically valid Python that compiles."""
    probe_code = generate_frontend_connectivity_probe()
    assert isinstance(probe_code, str)
    assert len(probe_code) > 0

    compiled = compile(probe_code, "<frontend_probe>", "exec")
    assert compiled is not None


def test_invalid_syntax_rejected() -> None:
    """Verify that invalid syntax arrangements (such as semicolon preceding compound with statement) fail compilation."""
    invalid_script = "import os; x = 1; with open('nonexistent') as f: pass"
    with pytest.raises(SyntaxError):
        compile(invalid_script, "<invalid_string>", "exec")


def test_probe_execution_success() -> None:
    """Verify that the generated probe executes cleanly and reports CONNECTIVITY_OK when backend is healthy."""
    probe_code = generate_frontend_connectivity_probe()
    response = DummyHTTPResponse(
        200, b'{"status": "healthy", "service": "finova-backend"}'
    )
    env = {"BACKEND_API_URL": "http://backend:8000/api/v1"}

    code, stdout, stderr, reqs = execute_probe_in_process(
        probe_code, env=env, mock_response=response
    )

    assert code == 0
    assert "CONNECTIVITY_OK:http://backend:8000/api/v1" in stdout
    assert stderr == ""
    assert len(reqs) == 1
    assert reqs[0].full_url == "http://backend:8000/api/v1/health"


def test_probe_execution_missing_backend_api_url() -> None:
    """Verify probe exits with code 1 and logs clear error when BACKEND_API_URL is missing or empty."""
    probe_code = generate_frontend_connectivity_probe()

    # Empty string
    code1, stdout1, stderr1, _ = execute_probe_in_process(
        probe_code, env={"BACKEND_API_URL": ""}
    )
    assert code1 == 1
    assert "ERROR: BACKEND_API_URL environment variable is missing or empty" in stderr1
    assert stdout1 == ""

    # Missing from env entirely
    code2, stdout2, stderr2, _ = execute_probe_in_process(probe_code, env={})
    assert code2 == 1
    assert "ERROR: BACKEND_API_URL environment variable is missing or empty" in stderr2


def test_probe_execution_unsuccessful_http_response() -> None:
    """Verify probe exits with code 1 when backend returns an unsuccessful HTTP status."""
    probe_code = generate_frontend_connectivity_probe()
    http_error = urllib.error.HTTPError(
        url="http://backend:8000/api/v1/health",
        code=503,
        msg="Service Unavailable",
        hdrs={},
        fp=io.BytesIO(b"Service Unavailable"),
    )
    env = {"BACKEND_API_URL": "http://backend:8000/api/v1"}

    code, stdout, stderr, _ = execute_probe_in_process(
        probe_code, env=env, mock_urlopen_side_effect=http_error
    )
    assert code == 1
    assert (
        "HTTP ERROR: Received status 503 from http://backend:8000/api/v1/health"
        in stderr
    )
    assert stdout == ""


def test_probe_execution_network_url_error() -> None:
    """Verify probe exits with code 1 and logs network details when backend cannot be reached."""
    probe_code = generate_frontend_connectivity_probe()
    url_error = urllib.error.URLError("Name or service not known")
    env = {"BACKEND_API_URL": "http://backend:8000/api/v1"}

    code, stdout, stderr, _ = execute_probe_in_process(
        probe_code, env=env, mock_urlopen_side_effect=url_error
    )
    assert code == 1
    assert "NETWORK ERROR: Failed to reach backend" in stderr
    assert "Name or service not known" in stderr
    assert stdout == ""


def test_probe_execution_malformed_json() -> None:
    """Verify probe exits with code 1 when backend returns non-JSON content."""
    probe_code = generate_frontend_connectivity_probe()
    response = DummyHTTPResponse(200, b"<html><body>502 Bad Gateway</body></html>")
    env = {"BACKEND_API_URL": "http://backend:8000/api/v1"}

    code, stdout, stderr, _ = execute_probe_in_process(
        probe_code, env=env, mock_response=response
    )
    assert code == 1
    assert "JSON ERROR: Malformed JSON payload received" in stderr
    assert stdout == ""


def test_probe_execution_backend_status_not_healthy() -> None:
    """Verify probe exits with code 1 when backend payload status is not healthy."""
    probe_code = generate_frontend_connectivity_probe()
    env = {"BACKEND_API_URL": "http://backend:8000/api/v1"}

    # Case A: status == "degraded"
    resp_degraded = DummyHTTPResponse(
        200, b'{"status": "degraded", "reasons": ["high load"]}'
    )
    code_deg, _, stderr_deg, _ = execute_probe_in_process(
        probe_code, env=env, mock_response=resp_degraded
    )
    assert code_deg == 1
    assert (
        "HEALTH ERROR: Backend status is 'degraded', expected \"healthy\"" in stderr_deg
    )

    # Case B: status == "unhealthy"
    resp_unhealthy = DummyHTTPResponse(200, b'{"status": "unhealthy"}')
    code_unh, _, stderr_unh, _ = execute_probe_in_process(
        probe_code, env=env, mock_response=resp_unhealthy
    )
    assert code_unh == 1
    assert (
        "HEALTH ERROR: Backend status is 'unhealthy', expected \"healthy\""
        in stderr_unh
    )


def test_probe_url_construction_and_trailing_slash_normalization() -> None:
    """Verify that various forms of BACKEND_API_URL are cleanly normalized to /health."""
    probe_code = generate_frontend_connectivity_probe()
    response = DummyHTTPResponse(200, b'{"status": "healthy"}')

    variants = [
        ("http://backend:8000/api/v1", "http://backend:8000/api/v1/health"),
        ("http://backend:8000/api/v1/", "http://backend:8000/api/v1/health"),
        ("http://backend:8000/api/v1/health", "http://backend:8000/api/v1/health"),
        ("http://backend:8000/api/v1/health/", "http://backend:8000/api/v1/health"),
    ]

    for input_url, expected_health_url in variants:
        code, stdout, stderr, reqs = execute_probe_in_process(
            probe_code, env={"BACKEND_API_URL": input_url}, mock_response=response
        )
        assert code == 0, f"Failed for {input_url}: {stderr}"
        assert len(reqs) == 1
        assert reqs[0].full_url == expected_health_url


def test_probe_subprocess_real_server_execution() -> None:
    """Verify generated probe executes successfully in a real standalone Python subprocess."""

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/api/v1/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "healthy", "service": "finova-backend"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass  # Suppress logging in test output

    server = HTTPServer(("127.0.0.1", 0), HealthHandler)
    server_port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        probe_code = generate_frontend_connectivity_probe()
        env = os.environ.copy()
        env["BACKEND_API_URL"] = f"http://127.0.0.1:{server_port}/api/v1"

        res = subprocess.run(
            [sys.executable, "-c", probe_code],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert res.returncode == 0
        assert f"CONNECTIVITY_OK:http://127.0.0.1:{server_port}/api/v1" in res.stdout
    finally:
        server.shutdown()
        server.server_close()


def test_probe_subprocess_missing_env_error() -> None:
    """Verify generated probe fails in a real standalone Python subprocess when BACKEND_API_URL is missing."""
    probe_code = generate_frontend_connectivity_probe()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }

    res = subprocess.run(
        [sys.executable, "-c", probe_code],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert res.returncode == 1
    assert "ERROR: BACKEND_API_URL environment variable is missing" in res.stderr


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


def test_acceptance_sequence_frontend_health_before_connectivity() -> None:
    """Verify run_acceptance_suite() executes frontend health check before internal connectivity check."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-seqtest")
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

        def side_effect(args, **kwargs):
            if "id" in args:
                return 0, "1000\n", "", None
            if "python" in args and "-c" in args:
                return 0, "CONNECTIVITY_OK:http://backend:8000/api/v1\n", "", None
            return 0, "ok", "", None

        mock_compose.side_effect = side_effect

        results = runner.run_acceptance_suite()
        names = [r.name for r in results]

        assert "docker_frontend_health_check" in names
        assert "docker_frontend_backend_connectivity" in names

        frontend_health_idx = names.index("docker_frontend_health_check")
        connectivity_idx = names.index("docker_frontend_backend_connectivity")
        assert frontend_health_idx < connectivity_idx, (
            f"Frontend health check (idx {frontend_health_idx}) must precede connectivity probe (idx {connectivity_idx})"
        )


def test_connectivity_failure_is_mandatory_fail_and_triggers_cleanup() -> None:
    """Verify that a connectivity failure is marked mandatory FAIL and triggers project cleanup in finally."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-connfail")
    runner.docker_cli = "/usr/bin/docker"

    down_called: list[bool] = []

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
            args=["docker", "info"], returncode=0, stdout="", stderr=""
        )
        mock_http.return_value = MagicMock(
            status_code=200, json=lambda: {"status": "healthy"}
        )

        def side_effect(args, **kwargs):
            if "down" in args:
                down_called.append(True)
                return 0, "down ok", "", None
            if "id" in args:
                return 0, "1000\n", "", None
            if "python" in args and "-c" in args:
                return 1, "", "NETWORK ERROR: Name or service not known", None
            return 0, "", "", None

        mock_compose.side_effect = side_effect

        results = runner.run_acceptance_suite()
        conn_res = next(
            (r for r in results if r.name == "docker_frontend_backend_connectivity"),
            None,
        )
        assert conn_res is not None
        assert conn_res.passed is False
        assert conn_res.status == "FAIL"
        assert conn_res.is_mandatory is True

        # Ensure persistence check was not reached
        persistence_res = next(
            (r for r in results if r.name == "docker_data_volume_persistence"),
            None,
        )
        assert persistence_res is None

        # Ensure cleanup executed in finally block
        cleanup_res = next(
            (r for r in results if r.name == "docker_environment_cleanup"),
            None,
        )
        assert cleanup_res is not None
        assert len(down_called) == 1


def test_compose_project_name_propagation_in_probe() -> None:
    """Verify that the connectivity probe command is executed within the runner's isolated project scope."""
    runner = DockerAcceptanceRunner(project_name="finova-acc-probe-proj-scope")
    runner.docker_cli = "/usr/bin/docker"

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = subprocess.CompletedProcess(
            args=["docker", "compose"],
            returncode=0,
            stdout="CONNECTIVITY_OK:http://backend:8000/api/v1\n",
            stderr="",
        )

        res = runner._check_frontend_backend_connectivity()
        assert res.passed is True
        assert res.status == "PASS"

        # Verify arguments passed to subprocess.run
        assert mock_sub.call_count == 1
        cmd_args = mock_sub.call_args[0][0]
        assert "-p" in cmd_args
        p_idx = cmd_args.index("-p")
        assert cmd_args[p_idx + 1] == "finova-acc-probe-proj-scope"
        assert "exec" in cmd_args
        assert "frontend" in cmd_args
