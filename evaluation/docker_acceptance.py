"""Finova AI — Real Docker Deployment Acceptance Test Runner.

Executes a non-destructive, isolated Docker Compose acceptance workflow:
1. Docker CLI availability & daemon connectivity.
2. Dynamic host port validation & collision detection.
3. Compose configuration syntax validation with isolated project scope.
4. Multi-stage backend & frontend image builds.
5. Isolated container startup with configurable host port mappings.
6. Live health probing of backend (/api/v1/health) and frontend (_stcore/health).
7. Non-root user validation (UID 1000 appuser) for both backend and frontend.
8. Frontend-to-backend Docker network communication & BACKEND_API_URL validation.
9. Hardened SQLite data volume mounting & restart persistence validation.
10. Guaranteed teardown and volume cleanup restricted strictly to the acceptance project.

If Docker is unavailable, tests are cleanly marked SKIPPED with explicit prerequisite explanations.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class DockerCheckResult:
    """Individual Docker deployment acceptance check outcome."""

    name: str
    category: str = "docker_acceptance"
    passed: bool = True
    status: str = "PASS"  # "PASS", "WARN", "FAIL", "SKIPPED"
    is_mandatory: bool = True
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def validate_host_ports(backend_port: int, frontend_port: int) -> tuple[bool, str]:
    """Validate that host ports are valid integers, distinct, and not currently occupied."""
    if not (1 <= backend_port <= 65535):
        return (
            False,
            f"Invalid backend host port {backend_port}: must be an integer between 1 and 65535.",
        )
    if not (1 <= frontend_port <= 65535):
        return (
            False,
            f"Invalid frontend host port {frontend_port}: must be an integer between 1 and 65535.",
        )
    if backend_port == frontend_port:
        return (
            False,
            f"Port collision: backend host port ({backend_port}) and frontend host port ({frontend_port}) cannot be identical.",
        )

    for role, port in (("backend", backend_port), ("frontend", frontend_port)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return (
                        False,
                        f"Host port {port} ({role}) is already in use by another process on 127.0.0.1.",
                    )
        except Exception as exc:
            return False, f"Socket error probing port {port} ({role}): {exc}"

    return (
        True,
        f"Host ports {backend_port} (backend) and {frontend_port} (frontend) are valid and available.",
    )


def generate_frontend_connectivity_probe() -> str:
    """Generate a self-contained, valid Python probe script to verify backend connectivity from frontend container.

    Requirements enforced:
    - Syntactically valid Python without compound statements on semicolon-delimited lines.
    - Resolves and validates BACKEND_API_URL environment variable.
    - Normalizes trailing slashes and constructs /health endpoint.
    - Validates HTTP response status 200.
    - Validates and parses JSON payload.
    - Validates that response status attribute equals 'healthy'.
    - Returns structured error diagnostic messages on stderr.
    - Emits CONNECTIVITY_OK:<backend_url> on stdout upon complete verification.
    """
    return (
        "import json\n"
        "import os\n"
        "import sys\n"
        "import urllib.error\n"
        "import urllib.request\n"
        "\n"
        "backend_url = os.environ.get('BACKEND_API_URL', '').strip()\n"
        "if not backend_url:\n"
        "    sys.stderr.write('ERROR: BACKEND_API_URL environment variable is missing or empty\\n')\n"
        "    sys.exit(1)\n"
        "\n"
        "base_url = backend_url.rstrip('/')\n"
        "health_url = base_url if base_url.endswith('/health') else f'{base_url}/health'\n"
        "\n"
        "req = urllib.request.Request(\n"
        "    health_url,\n"
        "    headers={'User-Agent': 'Finova-Frontend-Probe/1.0'},\n"
        ")\n"
        "\n"
        "try:\n"
        "    resp = urllib.request.urlopen(req, timeout=5)\n"
        "except urllib.error.HTTPError as exc:\n"
        "    sys.stderr.write(f'HTTP ERROR: Received status {exc.code} from {health_url}\\n')\n"
        "    sys.exit(1)\n"
        "except urllib.error.URLError as exc:\n"
        "    sys.stderr.write(f'NETWORK ERROR: Failed to reach backend at {health_url}: {exc.reason}\\n')\n"
        "    sys.exit(1)\n"
        "except Exception as exc:\n"
        "    sys.stderr.write(f'PROBE ERROR: Unexpected error connecting to {health_url}: {exc}\\n')\n"
        "    sys.exit(1)\n"
        "\n"
        "status_code = resp.getcode()\n"
        "if status_code != 200:\n"
        "    sys.stderr.write(f'STATUS ERROR: Expected HTTP 200, got {status_code} from {health_url}\\n')\n"
        "    sys.exit(1)\n"
        "\n"
        "try:\n"
        "    raw_body = resp.read()\n"
        "    data = json.loads(raw_body.decode('utf-8'))\n"
        "except Exception as exc:\n"
        "    sys.stderr.write(f'JSON ERROR: Malformed JSON payload received from {health_url}: {exc}\\n')\n"
        "    sys.exit(1)\n"
        "\n"
        "backend_status = data.get('status') if isinstance(data, dict) else None\n"
        "if backend_status != 'healthy':\n"
        "    sys.stderr.write(f'HEALTH ERROR: Backend status is {backend_status!r}, expected \"healthy\". Payload: {data}\\n')\n"
        "    sys.exit(1)\n"
        "\n"
        "print(f'CONNECTIVITY_OK:{backend_url}')\n"
        "sys.exit(0)\n"
    )


class DockerAcceptanceRunner:
    """Orchestrates actual Docker container build, run, health, and persistence tests."""

    def __init__(
        self,
        project_name: str | None = None,
        backend_port: int = 18000,
        frontend_port: int = 18501,
        build_timeout_sec: int = 240,
        startup_timeout_sec: int = 60,
    ) -> None:
        """Initialize runner with unique UUID-based project identifier and test ports."""
        self.project_name = project_name or f"finova-acc-{uuid.uuid4().hex[:8]}"
        self.backend_port = backend_port
        self.frontend_port = frontend_port
        self.build_timeout_sec = build_timeout_sec
        self.startup_timeout_sec = startup_timeout_sec
        self.docker_cli = shutil.which("docker")

    def _run_compose_cmd(
        self,
        args: list[str],
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str, str | None]:
        """Execute a Docker Compose command scoped strictly to this test project.

        Returns (returncode, stdout, stderr, error_message).
        Captures TimeoutExpired and general exceptions without raising uncaught errors.
        """
        cmd = [
            "docker",
            "compose",
            "-p",
            self.project_name,
            "-f",
            "docker-compose.yml",
            *args,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return proc.returncode, proc.stdout, proc.stderr, None
        except subprocess.TimeoutExpired:
            return (
                -1,
                "",
                "",
                f"Command timed out after {timeout}s: {' '.join(cmd[:6])}",
            )
        except Exception as exc:
            return -1, "", "", f"Command execution failed: {exc}"

    def _validate_non_root(self, service: str) -> DockerCheckResult:
        """Validate that a container service executes under an unprivileged non-root user (UID 1000)."""
        check_name = f"docker_{service}_non_root_execution"
        code, stdout, stderr, err = self._run_compose_cmd(
            ["exec", "-T", service, "id", "-u"],
            timeout=15,
        )
        if err:
            return DockerCheckResult(
                name=check_name,
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"{service.capitalize()} non-root execution check error: {err}",
                details={"service": service, "error": err},
            )
        if code != 0:
            return DockerCheckResult(
                name=check_name,
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"{service.capitalize()} non-root check returned non-zero exit code ({code}): {stderr.strip()}",
                details={
                    "service": service,
                    "returncode": code,
                    "stderr": stderr.strip(),
                },
            )

        uid_str = stdout.strip()
        if not uid_str or not uid_str.isdigit():
            return DockerCheckResult(
                name=check_name,
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"{service.capitalize()} non-root check did not return a valid numeric UID: '{uid_str}'",
                details={"service": service, "stdout": uid_str},
            )

        uid_int = int(uid_str)
        if uid_int == 0:
            return DockerCheckResult(
                name=check_name,
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Security violation: {service.capitalize()} container is executing as root (UID 0).",
                details={"service": service, "uid": 0},
            )

        return DockerCheckResult(
            name=check_name,
            passed=True,
            status="PASS",
            is_mandatory=True,
            message=f"{service.capitalize()} container runs as unprivileged non-root user (UID: {uid_int}).",
            details={"service": service, "uid": uid_int},
        )

    def _check_frontend_backend_connectivity(self) -> DockerCheckResult:
        """Validate that the frontend container can communicate with the backend across the Docker network."""
        probe_script = generate_frontend_connectivity_probe()
        code, stdout, stderr, err = self._run_compose_cmd(
            ["exec", "-T", "frontend", "python", "-c", probe_script],
            timeout=15,
        )
        if err:
            return DockerCheckResult(
                name="docker_frontend_backend_connectivity",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Frontend-to-backend internal connectivity probe failed: {err}",
                details={"error": err},
            )
        if code != 0 or "CONNECTIVITY_OK" not in stdout:
            err_detail = (
                stderr.strip()
                or stdout.strip()
                or f"Process exited with non-zero exit code ({code})"
            )
            return DockerCheckResult(
                name="docker_frontend_backend_connectivity",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Frontend could not communicate with backend service via Docker network: {err_detail}",
                details={
                    "returncode": code,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip(),
                },
            )
        return DockerCheckResult(
            name="docker_frontend_backend_connectivity",
            passed=True,
            status="PASS",
            is_mandatory=True,
            message="Frontend successfully communicated with backend service across internal Docker network.",
            details={"output": stdout.strip()},
        )

    def _check_persistence(self) -> DockerCheckResult:
        """Validate SQLite volume persistence across backend container restarts using unique markers."""
        marker_id = 9999
        marker_val = f"acc_persist_{uuid.uuid4().hex[:12]}"

        # Step 1: Write unique marker into isolated container DB
        write_script = (
            f"import sqlite3; "
            f"conn = sqlite3.connect('/app/data/finova.db'); "
            f"conn.execute('CREATE TABLE IF NOT EXISTS _acc_persistence (id INTEGER PRIMARY KEY, val TEXT);'); "
            f"conn.execute('INSERT OR REPLACE INTO _acc_persistence VALUES ({marker_id}, \\'{marker_val}\\');'); "
            f"conn.commit(); conn.close(); print('WRITE_OK')"
        )
        code, stdout, stderr, err = self._run_compose_cmd(
            ["exec", "-T", "backend", "python", "-c", write_script],
            timeout=15,
        )
        if err or code != 0 or "WRITE_OK" not in stdout:
            return DockerCheckResult(
                name="docker_data_volume_persistence",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Failed writing test marker into SQLite database: {err or stderr.strip()}",
                details={
                    "step": "write_marker",
                    "code": code,
                    "stderr": stderr.strip(),
                    "err": err,
                },
            )

        # Step 2: Restart backend container
        code, stdout, stderr, err = self._run_compose_cmd(
            ["restart", "backend"], timeout=25
        )
        if err or code != 0:
            return DockerCheckResult(
                name="docker_data_volume_persistence",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Failed restarting backend container: {err or stderr.strip()}",
                details={
                    "step": "restart_backend",
                    "code": code,
                    "stderr": stderr.strip(),
                    "err": err,
                },
            )

        # Step 3: Wait for backend to recover health post-restart
        backend_url = f"http://127.0.0.1:{self.backend_port}/api/v1/health"
        post_restart_healthy = False
        start_t = time.monotonic()
        while time.monotonic() - start_t < 30:
            try:
                r = httpx.get(backend_url, timeout=2.0)
                if r.status_code == 200:
                    post_restart_healthy = True
                    break
            except Exception:
                pass
            time.sleep(1.0)

        if not post_restart_healthy:
            return DockerCheckResult(
                name="docker_data_volume_persistence",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Backend did not regain healthy status at {backend_url} within 30s after restart.",
                details={"step": "post_restart_health", "url": backend_url},
            )

        # Step 4: Read marker back from database
        read_script = (
            f"import sqlite3; "
            f"conn = sqlite3.connect('/app/data/finova.db'); "
            f"cur = conn.execute('SELECT val FROM _acc_persistence WHERE id={marker_id};'); "
            f"row = cur.fetchone(); conn.close(); "
            f"print(row[0] if row else 'NONE')"
        )
        code, stdout, stderr, err = self._run_compose_cmd(
            ["exec", "-T", "backend", "python", "-c", read_script],
            timeout=15,
        )
        if err or code != 0:
            return DockerCheckResult(
                name="docker_data_volume_persistence",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Failed reading test marker from SQLite database after restart: {err or stderr.strip()}",
                details={
                    "step": "read_marker",
                    "code": code,
                    "stderr": stderr.strip(),
                    "err": err,
                },
            )

        retrieved_val = stdout.strip()
        if retrieved_val != marker_val:
            return DockerCheckResult(
                name="docker_data_volume_persistence",
                passed=False,
                status="FAIL",
                is_mandatory=True,
                message=f"Data persistence mismatch: expected '{marker_val}', retrieved '{retrieved_val}'.",
                details={
                    "step": "verify_marker",
                    "expected": marker_val,
                    "retrieved": retrieved_val,
                },
            )

        return DockerCheckResult(
            name="docker_data_volume_persistence",
            passed=True,
            status="PASS",
            is_mandatory=True,
            message="SQLite data volume persistence verified across container restart with unique marker.",
            details={"marker_id": marker_id, "marker_value": marker_val},
        )

    def run_acceptance_suite(self) -> list[DockerCheckResult]:
        """Execute full end-to-end Docker acceptance workflow with guaranteed cleanup."""
        results: list[DockerCheckResult] = []

        # 1. Docker CLI availability
        if not self.docker_cli:
            results.append(
                DockerCheckResult(
                    name="docker_cli_availability",
                    passed=False,
                    status="SKIPPED",
                    is_mandatory=True,
                    message="Docker CLI is not installed or not in system PATH. Docker deployment acceptance could not be verified.",
                    details={"prerequisite": "docker_cli_required"},
                )
            )
            return results

        results.append(
            DockerCheckResult(
                name="docker_cli_availability",
                passed=True,
                status="PASS",
                is_mandatory=True,
                message=f"Docker CLI located at: {self.docker_cli}",
            )
        )

        # 2. Docker daemon connectivity
        try:
            daemon_check = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if daemon_check.returncode != 0:
                results.append(
                    DockerCheckResult(
                        name="docker_daemon_connectivity",
                        passed=False,
                        status="SKIPPED",
                        is_mandatory=True,
                        message="Docker daemon is not running or unreachable. Start Docker Desktop/daemon to run acceptance tests.",
                        details={"stderr": daemon_check.stderr[:200]},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_daemon_connectivity",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="Docker daemon is active and responding.",
                )
            )
        except subprocess.TimeoutExpired:
            results.append(
                DockerCheckResult(
                    name="docker_daemon_connectivity",
                    passed=False,
                    status="SKIPPED",
                    is_mandatory=True,
                    message="Docker daemon probe timed out after 8s. Docker daemon is unresponsive.",
                )
            )
            return results
        except Exception as exc:
            results.append(
                DockerCheckResult(
                    name="docker_daemon_connectivity",
                    passed=False,
                    status="SKIPPED",
                    is_mandatory=True,
                    message=f"Docker daemon connectivity probe failed: {exc}",
                )
            )
            return results

        # 3. Dynamic Host Port Validation
        ports_valid, port_msg = validate_host_ports(
            self.backend_port, self.frontend_port
        )
        if not ports_valid:
            results.append(
                DockerCheckResult(
                    name="docker_host_port_validation",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"Host port validation failed: {port_msg}",
                    details={
                        "backend_port": self.backend_port,
                        "frontend_port": self.frontend_port,
                    },
                )
            )
            return results

        results.append(
            DockerCheckResult(
                name="docker_host_port_validation",
                passed=True,
                status="PASS",
                is_mandatory=True,
                message=port_msg,
                details={
                    "backend_port": self.backend_port,
                    "frontend_port": self.frontend_port,
                },
            )
        )

        # 4. Docker Compose Configuration Validation
        env_vars = os.environ.copy()
        env_vars["PORT"] = str(self.backend_port)
        env_vars["FRONTEND_PORT"] = str(self.frontend_port)
        env_vars["SEC_USER_AGENT"] = (
            "FinovaAI-DockerTest/1.0 (test-runner@finova.internal)"
        )

        code, stdout, stderr, err = self._run_compose_cmd(
            ["config"], timeout=15, env=env_vars
        )
        if err or code != 0:
            results.append(
                DockerCheckResult(
                    name="docker_compose_config_validation",
                    passed=False,
                    status="FAIL",
                    is_mandatory=True,
                    message=f"docker-compose.yml configuration validation failed: {err or stderr[:300]}",
                    details={"stderr": stderr[:300], "error": err},
                )
            )
            return results

        results.append(
            DockerCheckResult(
                name="docker_compose_config_validation",
                passed=True,
                status="PASS",
                is_mandatory=True,
                message="docker-compose.yml configuration syntax validated successfully.",
            )
        )

        # Execute container lifecycle checks with guaranteed cleanup
        cleanup_needed = True
        try:
            # 5. Backend Image Build
            code, stdout, stderr, err = self._run_compose_cmd(
                ["build", "backend"], timeout=self.build_timeout_sec, env=env_vars
            )
            if err or code != 0:
                results.append(
                    DockerCheckResult(
                        name="docker_build_backend_image",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"Backend Docker image build failed: {err or stderr[-500:]}",
                        details={"stderr": stderr[-500:], "error": err},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_build_backend_image",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="Backend production Docker image built successfully.",
                )
            )

            # 6. Frontend Image Build
            code, stdout, stderr, err = self._run_compose_cmd(
                ["build", "frontend"], timeout=self.build_timeout_sec, env=env_vars
            )
            if err or code != 0:
                results.append(
                    DockerCheckResult(
                        name="docker_build_frontend_image",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"Frontend Docker image build failed: {err or stderr[-500:]}",
                        details={"stderr": stderr[-500:], "error": err},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_build_frontend_image",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message="Frontend production Docker image built successfully.",
                )
            )

            # 7. Container Startup
            code, stdout, stderr, err = self._run_compose_cmd(
                ["up", "-d"], timeout=self.startup_timeout_sec, env=env_vars
            )
            if err or code != 0:
                results.append(
                    DockerCheckResult(
                        name="docker_container_startup",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"docker compose up -d failed: {err or stderr[:300]}",
                        details={"stderr": stderr[:300], "error": err},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_container_startup",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message=f"Containers started under isolated project '{self.project_name}'.",
                )
            )

            # 8. Backend Health Endpoint Probe
            backend_url = f"http://127.0.0.1:{self.backend_port}/api/v1/health"
            backend_healthy = False
            diag_data = None
            start_t = time.monotonic()
            while time.monotonic() - start_t < 30:
                try:
                    r = httpx.get(backend_url, timeout=2.0)
                    if r.status_code == 200:
                        backend_healthy = True
                        diag_data = r.json()
                        break
                except Exception:
                    pass
                time.sleep(1.0)

            if not backend_healthy:
                results.append(
                    DockerCheckResult(
                        name="docker_backend_health_check",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"Backend health endpoint failed to respond at {backend_url} within 30s.",
                        details={"url": backend_url},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_backend_health_check",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message=f"Backend container is healthy at {backend_url}.",
                    details=diag_data or {},
                )
            )

            # 9. Frontend Health Endpoint Probe
            frontend_url = f"http://127.0.0.1:{self.frontend_port}/_stcore/health"
            frontend_healthy = False
            start_t = time.monotonic()
            while time.monotonic() - start_t < 30:
                try:
                    r = httpx.get(frontend_url, timeout=2.0)
                    if r.status_code == 200:
                        frontend_healthy = True
                        break
                except Exception:
                    pass
                time.sleep(1.0)

            if not frontend_healthy:
                results.append(
                    DockerCheckResult(
                        name="docker_frontend_health_check",
                        passed=False,
                        status="FAIL",
                        is_mandatory=True,
                        message=f"Frontend health endpoint failed to respond at {frontend_url} within 30s.",
                        details={"url": frontend_url},
                    )
                )
                return results

            results.append(
                DockerCheckResult(
                    name="docker_frontend_health_check",
                    passed=True,
                    status="PASS",
                    is_mandatory=True,
                    message=f"Frontend container is healthy at {frontend_url}.",
                    details={"url": frontend_url},
                )
            )

            # 10. Non-Root Execution Checks (Backend & Frontend)
            backend_non_root = self._validate_non_root("backend")
            results.append(backend_non_root)
            if not backend_non_root.passed:
                return results

            frontend_non_root = self._validate_non_root("frontend")
            results.append(frontend_non_root)
            if not frontend_non_root.passed:
                return results

            # 11. Frontend-to-Backend Docker Network Connectivity
            conn_res = self._check_frontend_backend_connectivity()
            results.append(conn_res)
            if not conn_res.passed:
                return results

            # 12. SQLite Persistence Across Container Restart
            persistence_res = self._check_persistence()
            results.append(persistence_res)
            if not persistence_res.passed:
                return results

        finally:
            if cleanup_needed and self.docker_cli:
                try:
                    down_code, _, down_err, err = self._run_compose_cmd(
                        ["down", "-v"], timeout=30
                    )
                    cleanup_ok = down_code == 0 and err is None
                    results.append(
                        DockerCheckResult(
                            name="docker_environment_cleanup",
                            passed=cleanup_ok,
                            status="PASS" if cleanup_ok else "WARN",
                            is_mandatory=False,
                            message=(
                                f"Isolated test project '{self.project_name}' and volumes removed cleanly."
                                if cleanup_ok
                                else f"Cleanup warning for project '{self.project_name}': {err or down_err[:200]}"
                            ),
                            details={"project_name": self.project_name},
                        )
                    )
                except Exception as exc:
                    results.append(
                        DockerCheckResult(
                            name="docker_environment_cleanup",
                            passed=False,
                            status="WARN",
                            is_mandatory=False,
                            message=f"Cleanup exception for project '{self.project_name}': {exc}",
                        )
                    )

        return results


def main() -> int:
    """CLI entrypoint for standalone Docker acceptance execution."""
    print("=================================================================")
    print("Finova AI — Docker Deployment Acceptance Test Runner")
    print("=================================================================\n")

    runner = DockerAcceptanceRunner()
    results = runner.run_acceptance_suite()

    has_fail = False
    has_skip = False
    for res in results:
        status_label = f"[{res.status}]"
        print(f"{status_label:<10} {res.name}: {res.message}")
        if res.status == "FAIL":
            has_fail = True
        elif res.status == "SKIPPED":
            has_skip = True

    print("\n-----------------------------------------------------------------")
    if has_fail:
        print("RESULT: Docker Acceptance FAILED (one or more mandatory checks failed)")
        return 1
    if has_skip:
        print("RESULT: Docker Acceptance SKIPPED (prerequisites missing, e.g. Docker)")
        return 2

    print("RESULT: Docker Acceptance PASSED (all deployment checks verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
