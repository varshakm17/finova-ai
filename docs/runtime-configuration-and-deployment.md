# Finova AI — Runtime Configuration and Deployment Guide

## Overview

This guide provides definitive instructions for configuring, deploying, operating, and troubleshooting **Finova AI — Multi-Agent Financial Research and Intelligence System** across local development environments (Windows 11 / Linux / macOS) and containerized production environments (Docker & Docker Compose).

---

## 1. Environment Architecture & Configuration Management

Finova AI employs a centralized, type-safe configuration system managed by Pydantic Settings (`config/settings.py`). All configuration is loaded from environment variables or a local `.env` file with strict validation and safe development defaults.

### Key Environment Variables

| Variable | Default (Local) | Docker Default | Description |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | Deployment mode (`development`, `staging`, `production`) |
| `DEBUG` | `true` | `false` | Verbose debug logging |
| `HOST` | `127.0.0.1` | `0.0.0.0` | Backend API listen address |
| `PORT` | `8000` | `8000` | Backend API host published port (container listens on 8000) |
| `FRONTEND_PORT` | `8501` | `8501` | Streamlit UI host published port (container listens on 8501) |
| `BACKEND_API_URL` | `http://127.0.0.1:8000/api/v1` | `http://backend:8000/api/v1` | Backend URL used by Streamlit frontend |
| `SEC_USER_AGENT` | `""` *(Unset)* | `""` *(Unset)* | Identity declaration for SEC EDGAR (`AppName/Version (admin@org.com)`) |
| `CORS_ORIGINS` | `http://localhost:8501,...` | `http://localhost:8501,...` | Allowed CORS origins (comma-separated or JSON list) |
| `CORS_ALLOW_CREDENTIALS` | `true` | `true` | Allow credentials in CORS (coerced to False if wildcard `*` origin is used) |
| `DATABASE_URL` | `sqlite:///./finova.db` | `sqlite:////app/data/finova.db` | SQLite database connection string |
| `DATABASE_WAL_MODE` | `true` | `true` | Enable SQLite Write-Ahead Logging (WAL) for concurrency |
| `DATABASE_BUSY_TIMEOUT_MS`| `30000` | `30000` | SQLite lock wait timeout in milliseconds (30s) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | `http://host.docker.internal:11434` | Local Ollama LLM provider URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | `qwen2.5:3b` | Primary LLM model for CPU-efficient inference |
| `MAX_REQUEST_BODY_BYTES` | `10485760` (10MB) | `10485760` (10MB) | Maximum request body payload limit enforced at ASGI layer |

---

## 2. SEC EDGAR Fair Access Policy & Identity Compliance

The U.S. Securities and Exchange Commission (SEC) strictly enforces its Fair Access Policy:
- Every request must include a custom User-Agent in the exact format: `SampleCompany AdminContact@<sample company domain>.com`.
- Generic or placeholder identities (such as `contact@example.com`, `user@test.com`, `samplecompany.com`, or empty values) are rejected immediately by SEC servers with HTTP 403 Forbidden.

### Finova AI Identity Enforcement Rules
1. **No Dummy Defaults:** The default configuration for `SEC_USER_AGENT` is empty (`""`).
2. **Offline Startup & Testing:** Application startup and offline test suites execute cleanly without requiring a configured SEC identity.
3. **Outbound Guardrails:** Live outbound calls to `data.sec.gov` or `www.sec.gov` strictly validate `SEC_USER_AGENT`. If unconfigured or containing placeholder domains (`example.com`, `domain.com`, `test.com`), an explicit `SECConfigurationError` is raised with actionable guidance.
4. **Privacy Protection:** The `/api/v1/health` endpoint and all system logs automatically mask contact email addresses (e.g. `r***@f***.org`) via `SensitiveDataFilter`.

To configure your identity:
```env
SEC_USER_AGENT=FinovaAI-Research/1.0.0 (research-team@yourorganization.org)
```

---

## 3. ASGI Layer Request Payload Size Enforcement

Finova AI implements request-body size enforcement at the ASGI level via `backend/api/middleware.py`:
- **Limit:** Configurable via `MAX_REQUEST_BODY_BYTES` (default: 10 MB / 10,485,760 bytes).
- **Upfront Header Validation:** Inspects `Content-Length`. Requests declaring values exceeding the limit are rejected immediately with HTTP 413 Payload Too Large. Malformed or negative headers are rejected with HTTP 400 Bad Request.
- **Dynamic Stream Counting:** For chunked (`Transfer-Encoding: chunked`) or streamed requests where `Content-Length` is omitted or spoofed, the middleware wraps the ASGI `receive` callable, counting received bytes on the fly.
- **Memory Safety:** Streaming bytes are never buffered indefinitely in memory. As soon as received bytes exceed `MAX_REQUEST_BODY_BYTES`, the stream is halted and HTTP 413 is returned.
- **Downstream Protection:** Rejected requests never execute downstream route handlers.

---

## 4. Local Deployment (Windows 11 / Linux / macOS)

### Prerequisites
- Python 3.11.x installed (`python --version`)
- Git (`git --version`)
- Ollama installed locally (optional, fallback deterministic templates operate if Ollama is absent)

### Step-by-Step Setup

1. **Clone and Navigate:**
   ```bash
   git clone https://github.com/varshakm17/finova-ai.git
   cd finova-ai
   ```

2. **Create Virtual Environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies:**
   ```powershell
   pip install --upgrade pip
   pip install -r requirements.lock
   pip install -r requirements-dev.txt
   ```

4. **Configure Environment:**
   ```powershell
   cp .env.example .env
   # Edit .env and supply your genuine SEC_USER_AGENT
   ```

5. **Initialize Database:**
   ```powershell
   python -c "from backend.data.storage import init_db; init_db()"
   ```

6. **Start Backend API:**
   ```powershell
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```

7. **Start Frontend Assistant (in separate terminal):**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   streamlit run frontend/app.py --server.port 8501
   ```

8. **Verify System Health:**
   - Backend Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Health Endpoint: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
   - Frontend UI: [http://localhost:8501](http://localhost:8501)

---

## 5. Docker & Docker Compose Deployment

The Docker setup encapsulates the FastAPI backend and Streamlit frontend in hardened, unprivileged container environments.

```
                          +-------------------------------------------------+
                          |             Docker Bridge Network               |
                          |                                                 |
  User Browser ---------> |  [Frontend: 8501]                               |
                          |        |                                        |
                          |        | (BACKEND_API_URL=http://backend:8000)  |
                          |        v                                        |
  User / API  ----------> |  [Backend: 8000]                                |
                          |        |                                        |
                          |        +--> [Shared Volume: /app/data]          |
                          |        |    - finova.db (WAL mode)              |
                          |        |    - sec_filings/                      |
                          |        v                                        |
  Host Ollama <-----------+-- host.docker.internal:11434                    |
                          +-------------------------------------------------+
```

### 5.1 Host System Prerequisites (Windows 11 Baseline)

To run the containerized Finova AI stack on Windows 11, the host machine must satisfy the following baseline specifications:

| Component | Minimum Requirement | Recommended Specification |
|---|---|---|
| **Operating System** | Windows 11 64-bit (Build 22000+) Home, Pro, or Enterprise | Windows 11 Pro 64-bit with WSL 2 |
| **Virtualization** | Hardware Virtualization (VT-x / AMD-V) enabled in BIOS/UEFI | Enabled |
| **WSL 2 Subsystem** | WSL 2 Linux kernel installed (`wsl --status`) | Ubuntu or Debian distro installed |
| **Container Engine** | Docker Desktop 4.x+ for Windows with WSL 2 backend | Docker Desktop 4.35+ |
| **Memory (RAM)** | 16 GB Physical RAM (allocated: 4 GB+ to WSL 2 engine) | 16 GB+ |
| **Available Storage** | 20 GB free disk space on system drive | 30 GB+ SSD |
| **Compute Type** | CPU-only laptop execution supported (no discrete GPU required) | Multi-core x86_64 CPU |

### 5.2 Docker Desktop for Windows Installation & WSL 2 Setup

If Docker is not currently installed on the host system:

1. **Verify or Install WSL 2:**
   Open PowerShell as Administrator and run:
   ```powershell
   wsl --install --no-distribution
   wsl --status
   ```
   Ensure `Default Version: 2` is reported. If no Linux distribution exists, install Ubuntu:
   ```powershell
   wsl --install -d Ubuntu
   ```

2. **Download & Install Docker Desktop:**
   - Download the official installer from [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
   - During installation, ensure the option **"Use WSL 2 instead of Hyper-V"** is checked.
   - Restart the machine if prompted.

3. **Configure Docker Desktop Settings:**
   - Open Docker Desktop.
   - Navigate to **Settings > General** and verify **"Use the WSL 2 based engine"** is enabled.
   - Navigate to **Settings > Resources > WSL Integration** and enable integration with your default WSL 2 distribution.
   - Optional: Limit WSL 2 memory consumption to prevent host laptop memory pressure by creating `%USERPROFILE%\.wslconfig`:
     ```ini
     [wsl2]
     memory=6GB
     processors=4
     ```

4. **Verify Docker Installation in PowerShell:**
   ```powershell
   docker --version
   docker compose version
   docker info
   docker context ls
   ```

### 5.3 Environment Configuration & SEC Identity Setup

Before building or launching containers:

1. **Create Container Environment File:**
   Copy the Docker Compose template:
   ```powershell
   copy .env.docker.example .env
   ```

2. **Configure SEC Regulatory Identity:**
   Edit `.env` and provide a genuine researcher or institutional identity adhering to the SEC EDGAR fair-access policy (`SampleCompany AdminContact@<sample company domain>.com`):
   ```env
   SEC_USER_AGENT=FinovaAI-Research/1.0.0 (researcher@myorganization.org)
   ```
   > [!IMPORTANT]
   > Do not use placeholder emails (such as `contact@example.com` or `user@test.com`). Live SEC EDGAR queries will be rejected with HTTP 403 Forbidden.

3. **Review Configurable Host Port Bindings:**
   The container stack listens internally on standard ports (backend: 8000, frontend: 8501). Host published ports can be modified in `.env` to avoid host port collisions:
   ```env
   PORT=8000
   FRONTEND_PORT=8501
   ```

### 5.4 Build, Container Startup & Health Verification Commands

1. **Build Container Images (Clean Build):**
   ```bash
   docker compose build --no-cache
   ```

2. **Start Services in Detached Mode:**
   ```bash
   docker compose up -d
   ```

3. **Inspect Running Containers & Startup Logs:**
   ```bash
   docker compose ps
   docker compose logs --no-color
   ```

4. **Verify Health Endpoints from Host Browser or CLI:**
   - **FastAPI Backend Health:**
     ```powershell
     curl -f http://localhost:8000/api/v1/health
     ```
     Expected JSON response: `{"status": "healthy", ...}`.
   - **Streamlit Frontend Health:**
     ```powershell
     curl -f http://localhost:8501/_stcore/health
     ```
     Expected HTTP status: `200 OK`.
   - **Interactive Frontend UI:** Open `http://localhost:8501` in your web browser.
   - **Interactive API Documentation:** Open `http://localhost:8000/docs`.

5. **Execute Automated Deployment Acceptance Suite:**
   ```powershell
   python evaluation/docker_acceptance.py
   # Or via the unified smoke test runner:
   python evaluation/deployment_smoke_tests.py --mode docker
   ```

6. **Scoped Project Teardown (Preserving Persistent Data):**
   ```bash
   docker compose down
   ```
   > [!WARNING]
   > Do not pass `-v` or `--volumes` during normal teardown unless you explicitly intend to delete the persistent SQLite database and indexed filings.

### 5.5 Compose Project Isolation & Resource Boundaries

- **No Fixed Container Names:** Explicit `container_name` declarations are omitted from `docker-compose.yml`. Standard deployments use the default directory project name (`finova-ai`).
- **Acceptance Isolation:** The automated acceptance test runner (`evaluation/docker_acceptance.py`) instantiates isolated UUID-based project identifiers (`finova-acc-<uuid>`).
- **Resource Boundary:** Test teardown targets only the isolated project (`docker compose -p <project> down -v`). Destructive global operations (such as `docker system prune` or global volume removal) are strictly prohibited.

### 5.6 Acceptance Verification Suite Gates

When Docker is available, `evaluation/docker_acceptance.py` verifies 10 mandatory deployment gates:
1. **Docker CLI & Daemon Availability:** Verifies Docker CLI path and active daemon connectivity.
2. **Dynamic Host Port Validation:** Validates port ranges (1–65535), detects collisions, and tests local socket occupancy.
3. **Compose Configuration Validation:** Executes `docker compose config` with project environment variables.
4. **Multi-Stage Container Builds:** Compiles backend and frontend production images.
5. **Isolated Container Startup:** Launches project containers in detached mode.
6. **Backend Health Probe:** Probes `http://127.0.0.1:<PORT>/api/v1/health` with retry polling.
7. **Frontend Health Probe:** Probes `http://127.0.0.1:<FRONTEND_PORT>/_stcore/health` with retry polling.
8. **Non-Root Execution Validation:** Verifies numeric UID from `id -u` on both backend and frontend containers, failing on non-zero exit codes, non-numeric outputs, or UID 0 (root).
9. **Frontend-to-Backend Network Connectivity:** Executes an internal lightweight probe inside the frontend container, validating `BACKEND_API_URL` propagation and internal Docker DNS resolution to `http://backend:8000/api/v1/health`.
10. **Hardened SQLite Volume Persistence:** Writes a unique per-run marker (`acc_persist_<uuid>`), restarts the backend container, polls for health recovery, reads the marker back, and asserts an exact byte match.
11. **Guaranteed Scoped Teardown:** Executes `docker compose -p <project> down -v` in a `finally` block, reporting warnings if teardown encounters errors.

### 5.7 Actual Acceptance Results (Session 17 Audit)

A live audit of the current developer workstation was conducted during Session 17:

- **Host Environment:** Windows 11 (NT 10.0.26200.0), 16 GB Physical RAM, CPU-only laptop.
- **Docker Engine State:** Docker CLI and Docker Desktop daemon are **not installed** on this host (`CommandNotFoundException`).
- **WSL Status:** WSL 2 kernel is present (`Default Version: 2`), but no Linux distributions are currently installed.
- **Static Configuration Checks:** 10/10 static deployment and Compose configuration checks **PASSED** (1 non-critical warning for development placeholder SEC User-Agent).
- **Offline Test Suite:** 504 passed, 12 skipped, 0 failed in 213 seconds.
- **Overall Deployment Status:** **`NOT_VERIFIED`** (Process exit code: `2`).

> [!NOTE]
> On host machines without Docker CLI or a running Docker daemon, live Docker acceptance checks report `SKIPPED` with overall state `NOT_VERIFIED` (exit code 2). This prevents false deployment certifications. In offline test environments, the frontend-to-backend probe script is independently compiled and executed against simulated responses and standalone HTTP subprocesses in `tests/test_docker_acceptance.py`. Live internal Docker network verification occurs exclusively when the container suite is launched on a host with an active Docker daemon.

### 5.8 Container Security & Non-Root Execution

Both `Dockerfile.backend` and `Dockerfile.frontend` enforce unprivileged execution:
- **Dedicated Application User:** Creates user `appuser` with explicit UID `1000` and GID `1000`.
- **Directory Ownership:** Pre-creates `/app/data`, `/app/datasets/filings`, `/app/datasets/indexes`, `/app/logs`, and `/app/reports` with ownership assigned to `appuser:appuser`.
- **User Instruction:** Enforces `USER appuser` prior to exposing ports or declaring runtime entrypoints.
- **No Secret Baking:** Build context excludes `.env`, `*.db`, `*.sqlite*`, and credentials via `.dockerignore`.
- **Unprivileged Ports:** Exposed ports 8000 and 8501 are non-privileged (> 1024).

### 5.9 SQLite Persistence & Volume Management

- **Named Volume Topology:** `finova_data` volume is mounted to container path `/app/data/`.
- **Database Connection String:** `DATABASE_URL=sqlite:////app/data/finova.db`.
- **Write-Ahead Logging:** `DATABASE_WAL_MODE=true` ensures database integrity and concurrent access across processes.
- **Restart Survival:** Stopping and restarting containers (`docker compose restart` or `docker compose down` followed by `docker compose up -d`) preserves all SQLite data, cached filings, and analytical runs in `finova_data`.

### 5.10 Known Limitations & Operational Constraints

1. **CPU-Only Execution:** Finova AI embeddings (`all-MiniLM-L6-v2`) and cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) execute purely on CPU. Vector indexing and search are optimized with FAISS CPU and numpy; GPU acceleration is neither required nor enabled in the default containers.
2. **Container Memory Footprint:** The combined container stack requires ~2.5 GB to 3.5 GB of RAM under active multi-agent research operations. On Windows 11 with WSL 2, ensure `.wslconfig` allocates at least 4 GB to the WSL 2 virtual machine.
3. **Local Deployment Scope:** Finova AI container deployment is scoped to local single-host Docker Compose operation. Cloud clustering, Kubernetes orchestration, or multi-node distributed storage are outside current project scope.

### 5.11 Dependency Integrity Strategy
- **Pip Pinning:** Docker builds explicitly pin `pip==24.3.1` in `Dockerfile.backend` and `Dockerfile.frontend` to eliminate build-time installer drift.
- **Exact Lockfile:** Runtime dependencies are locked to exact versions in `requirements.lock` (99 runtime packages).
- **Evaluation of Hash-Checking:** While `--require-hashes` enhances supply-chain security, multi-platform wheels for packages such as PyTorch, FAISS-CPU, and SciPy produce distinct platform-specific SHA256 hashes across Linux (x86_64 Debian containers) and development hosts (Windows 11). Pinning exact versions combined with a pinned pip installer provides stable, reproducible resolution in CPU-only containers without cross-platform wheel mismatch failures.

### Updating the Dependency Lockfile
To update or regenerate `requirements.lock`:
```powershell
# 1. Update tested version ranges in requirements.txt
# 2. In a clean Python 3.11 virtual environment, install requirements.txt:
pip install -r requirements.txt
# 3. Freeze runtime dependencies:
pip freeze > requirements.lock
# 4. Verify dev tools (pytest, ruff) are not in requirements.lock
```

---

## 6. Deployment Readiness State Machine

Finova AI evaluates environment readiness using an explicit 4-state state machine:

| State | Definition | Deployable? | Exit Code | Action |
|---|---|:---:|:---:|---|
| **`READY`** | All mandatory checks passed without warnings. | **YES** | `0` | Ready for production traffic. |
| **`DEGRADED`** | Core mandatory checks passed, but non-critical warnings remain (e.g. unconfigured SEC identity in dev). | **YES** | `0` | Operable with degraded optional subsystems. |
| **`NOT_VERIFIED`** | Mandatory acceptance checks were skipped (e.g. Docker daemon absent). | **NO** | `2` | Fulfill prerequisites and re-verify. |
| **`BLOCKED`** | One or more mandatory checks failed (e.g. build failure, port collision). | **NO** | `1` | Fix critical failure before release. |

### Running Deployment Acceptance Checks

```powershell
# 1. Validate static files, schemas, and configurations
python evaluation/deployment_smoke_tests.py --mode static

# 2. Validate local SQLite persistence, directories, and frontend resolver (Safe / Isolated)
python evaluation/deployment_smoke_tests.py --mode local

# 3. Run full Docker deployment acceptance (where Docker is available)
python evaluation/deployment_smoke_tests.py --mode docker

# 4. Run comprehensive multi-environment evaluation
python evaluation/deployment_smoke_tests.py --mode all

# 5. Machine-readable JSON output
python evaluation/deployment_smoke_tests.py --mode all --json
```

---

## 7. Safe Diagnostics & SQLite Persistence

- **Zero DB Pollution:** Deployment diagnostics execute against isolated temporary SQLite instances (`finova_diag_db_*`), guaranteeing that the user's actual `finova.db` database is never altered, touched, or populated with test artifacts.
- **Write-Ahead Logging (WAL):** Enabled via `PRAGMA journal_mode = WAL;`. Readers never block writers, and writers never block readers.
- **Busy Timeout:** Configured to 30,000 ms (`PRAGMA busy_timeout = 30000;`) to prevent lock collisions during concurrent queries.
- **Transaction Rollback:** All operations execute within atomic transaction rollback handlers.

---

## 8. Frontend-Backend URL Resolver Edge Cases

The URL resolver (`frontend/backend_client.py`) provides robust resolution:
- **Precedence:** `custom_url` parameter > `BACKEND_API_URL` env var > `settings.BACKEND_API_URL` > Local default (`127.0.0.1:8000`).
- **Scheme Validation:** Strictly permits `http` and `https`. Rejects `ftp://`, `ws://`, or malformed schemes with `ValueError`.
- **Port Validation:** Validates port range (1–65535). Rejects invalid or out-of-range ports with `ValueError`.
- **Parameter Stripping:** Automatically removes query strings (`?debug=true`) and fragments (`#top`) when deriving base and API endpoints.
- **No Duplicate Prefixes:** `endpoints.endpoint("/api/v1/health")` and `endpoints.endpoint("health")` both cleanly resolve to `http://<host>:<port>/api/v1/health`.

---

## 9. Troubleshooting Guide

### 1. Frontend Displays "Backend Offline / Degraded"
- **Cause:** `BACKEND_API_URL` is pointing to an unreachable host or port.
- **Resolution:**
  - Local mode: Ensure `BACKEND_API_URL=http://127.0.0.1:8000/api/v1`.
  - Docker mode: Ensure `BACKEND_API_URL=http://backend:8000/api/v1`.
  - Check trailing slashes: The resolver automatically normalizes slashes.

### 2. SEC EDGAR Returns 403 Forbidden
- **Cause:** `SEC_USER_AGENT` contains a placeholder like `contact@example.com` or invalid format.
- **Resolution:** Update `.env` with a compliant string: `AppName/1.0 (admin@verifieddomain.com)`.

### 3. Payload Too Large (HTTP 413)
- **Cause:** Request body exceeds `MAX_REQUEST_BODY_BYTES` (10MB).
- **Resolution:** Increase `MAX_REQUEST_BODY_BYTES` in `.env` if legitimate large filing uploads are required.

### 4. Deployment Readiness Reports `NOT_VERIFIED`
- **Cause:** Docker acceptance checks were skipped because Docker CLI or Docker Desktop is not active.
- **Resolution:** Start Docker Desktop or install the Docker CLI if Docker deployment verification is required. In local-only environments, run `python evaluation/deployment_smoke_tests.py --mode local` to verify local readiness.

### 5. Database Locked (`sqlite3.OperationalError: database is locked`)
- **Cause:** WAL mode disabled or timeout too short.
- **Resolution:** Ensure `DATABASE_WAL_MODE=true` and `DATABASE_BUSY_TIMEOUT_MS=30000` in `.env`.

### 6. Host Port Collision in Docker Deployment
- **Cause:** Port 8000 or 8501 is already bound by another local process on the host machine.
- **Resolution:** Override host ports in `.env` without changing container internal ports:
  ```env
  PORT=18000
  FRONTEND_PORT=18501
  ```
  The containers will continue listening internally on 8000 and 8501, while publishing to the specified host ports.

### 7. Docker Compose Project Isolation
- **Cause:** Conflict with an existing user container.
- **Resolution:** Finova AI uses automatic project prefixes. If needed, specify a custom Compose project name:
  ```bash
  docker compose -p my_finova_project up -d
  ```

### 8. Docker CLI Not Recognized in PowerShell
- **Cause:** Docker Desktop is not installed, or its binaries directory is not added to the Windows system `PATH`.
- **Resolution:**
  1. Verify whether Docker Desktop is installed in `C:\Program Files\Docker\Docker`.
  2. If missing, download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
  3. Ensure `C:\Program Files\Docker\Docker\resources\bin` is present in the `PATH` environment variable.
  4. Restart your PowerShell terminal and run `docker --version`.

### 9. WSL 2 Subsystem Reports "No Installed Distributions"
- **Cause:** The WSL 2 kernel is enabled, but no default Linux distribution exists to run containerized workloads.
- **Resolution:**
  1. Open PowerShell as Administrator.
  2. Install the standard Ubuntu distribution:
     ```powershell
     wsl --install -d Ubuntu
     ```
  3. Set WSL 2 as the default architecture:
     ```powershell
     wsl --set-default-version 2
     ```
  4. Re-open Docker Desktop and verify WSL 2 integration under **Settings > Resources > WSL Integration**.

### 10. Container Build Terminates During PyTorch / SciPy Wheel Installation
- **Cause:** The WSL 2 virtual machine has exhausted its allocated RAM while unpacking or compiling large wheel packages.
- **Resolution:** Create or edit `%USERPROFILE%\.wslconfig` on the Windows host to allocate sufficient memory (at least 4 GB to 6 GB) and swap:
  ```ini
  [wsl2]
  memory=6GB
  swap=4GB
  processors=4
  ```
  Restart the WSL service with `wsl --shutdown` before re-running `docker compose build --no-cache`.

### 11. Persistent Volume Permission Issues (Non-Root UID 1000)
- **Cause:** Host bind mounts or named volumes created with root ownership prevent the container's unprivileged user (`appuser`, UID 1000) from writing to `/app/data`.
- **Resolution:** The Dockerfile automatically pre-creates `/app/data` and assigns ownership to `appuser:appuser`. Use the named Docker volume `finova_data` defined in `docker-compose.yml` rather than arbitrary host folder bind-mounts to guarantee proper permission mapping.
