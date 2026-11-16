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

### Configurable Host Port Mappings
Finova AI containers listen internally on standard ports (backend: 8000, frontend: 8501). Host published ports are fully configurable without modifying container internals:
- `PORT` (default `8000`): Host port mapped to backend container port 8000 (`"${PORT:-8000}:8000"`).
- `FRONTEND_PORT` (default `8501`): Host port mapped to frontend container port 8501 (`"${FRONTEND_PORT:-8501}:8501"`).
This allows the acceptance suite or multi-tenant deployments to override host ports (e.g., 18000 and 18501) with zero risk of port collision.

### Compose Project Isolation
- **No Fixed Container Names:** Explicit `container_name` declarations are omitted from `docker-compose.yml`. Standard deployments use the default directory project name (`finova-ai`).
- **Acceptance Isolation:** The automated acceptance test suite instantiates isolated UUID-based project identifiers (`finova-acc-<uuid>`).
- **Resource Boundary:** Test teardown targets only the isolated project (`docker compose -p <project> down -v`). Destructive global operations (such as `docker system prune` or global volume removal) are strictly prohibited.

### Acceptance Verification Suite
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

> [!NOTE]
> On host machines without Docker CLI or a running Docker daemon, live Docker acceptance checks report `SKIPPED` with overall state `NOT_VERIFIED` (exit code 2). This prevents false deployment certifications. In offline test environments, the frontend-to-backend probe script is independently compiled and executed against simulated responses and standalone HTTP subprocesses in `tests/test_docker_acceptance.py`. Live internal Docker network verification occurs exclusively when the container suite is launched on a host with an active Docker daemon.

### Dependency Integrity Strategy
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

### Execution
```bash
# 1. Copy Docker template
cp .env.docker.example .env

# 2. Build and launch
docker compose up --build -d

# 3. Check container status
docker compose ps

# 4. View logs
docker compose logs -f backend
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
