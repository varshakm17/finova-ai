# Finova AI — Runtime Configuration and Deployment Guide

## Overview

This guide provides definitive instructions for configuring, deploying, operating, and troubleshooting **Finova AI — Multi-Agent Financial Research and Intelligence System** across local environments (Windows 11 / Linux / macOS) and containerized production environments (Docker & Docker Compose).

---

## 1. Environment Architecture & Configuration Management

Finova AI employs a centralized, type-safe configuration system managed by Pydantic Settings (`config/settings.py`). All configuration is loaded from environment variables or a local `.env` file with strict validation and safe defaults.

### Key Environment Variables

| Variable | Default (Local) | Docker Default | Description |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | Deployment mode (`development`, `staging`, `production`) |
| `DEBUG` | `false` | `false` | Verbose debug logging |
| `HOST` | `127.0.0.1` | `0.0.0.0` | Backend API listen address |
| `PORT` | `8000` | `8000` | Backend API port |
| `FRONTEND_PORT` | `8501` | `8501` | Streamlit UI port |
| `BACKEND_API_URL` | `http://127.0.0.1:8000/api/v1` | `http://backend:8000/api/v1` | Backend URL used by Streamlit frontend |
| `SEC_USER_AGENT` | *(Required)* | *(Required)* | Identity declaration for SEC EDGAR (`AppName/Version (admin@org.com)`) |
| `CORS_ORIGINS` | `http://localhost:8501,...` | `http://localhost:8501,...` | Allowed CORS origins (comma-separated or JSON list) |
| `CORS_ALLOW_CREDENTIALS` | `false` | `false` | Allow credentials in CORS (auto-disabled if `*` is present) |
| `DATABASE_PATH` | `finova.db` | `/app/data/finova.db` | SQLite database file location |
| `DATABASE_WAL_MODE` | `true` | `true` | Enable SQLite Write-Ahead Logging (WAL) for concurrency |
| `DATABASE_BUSY_TIMEOUT_MS`| `30000` | `30000` | SQLite lock wait timeout in milliseconds (30s) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | `http://host.docker.internal:11434` | Local Ollama LLM provider URL |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | `qwen2.5:1.5b` | Primary LLM model for CPU-efficient inference |
| `MAX_REQUEST_BODY_BYTES` | `10485760` (10MB) | `10485760` (10MB) | API request payload limit |

---

## 2. SEC EDGAR Fair Access Policy & Identity Compliance

The U.S. Securities and Exchange Commission (SEC) strictly enforces its Fair Access Policy:
- Every request must include a custom User-Agent in the exact format: `SampleCompany AdminContact@<sample company domain>.com`.
- Generic or placeholder identities (such as `contact@example.com`, `user@test.com`, or empty values) are rejected immediately by SEC servers with HTTP 403 Forbidden.

### Finova AI Enforcement Rules
1. **Startup Validation:** If `SEC_USER_AGENT` contains a placeholder domain (`example.com`, `test.com`, etc.), the system initializes in a `Degraded` mode for offline operations, logging an explicit warning.
2. **Outbound Guardrails:** Live requests to `data.sec.gov` or `www.sec.gov` are blocked if a placeholder is detected, raising `SECConfigurationError` with clear instructions rather than spamming SEC servers.
3. **Privacy Masking:** The `/api/v1/health` endpoint and logs automatically mask personal/institutional email addresses (e.g. `r***@f***.org`) to prevent credential leakage.

To configure your identity:
```env
SEC_USER_AGENT=FinovaAI-Research/1.0.0 (research-team@yourorganization.org)
```

---

## 3. Local Deployment (Windows 11 / Linux / macOS)

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
   pip install -r requirements.txt
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

## 4. Docker & Docker Compose Deployment

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

### Configuration
1. Copy the Docker environment template:
   ```bash
   cp .env.docker.example .env
   ```
2. Edit `.env` and set your `SEC_USER_AGENT`:
   ```env
   SEC_USER_AGENT=FinovaAI-Docker/1.0.0 (fintech-ops@yourorg.com)
   ```

### Execution
Build and launch the complete stack:
```bash
docker compose up --build -d
```

### Verifying Container Services
- Check container status:
  ```bash
  docker compose ps
  ```
- View real-time logs:
  ```bash
  docker compose logs -f backend
  docker compose logs -f frontend
  ```
- Verify backend health:
  ```bash
  curl http://localhost:8000/api/v1/health
  ```

### Stop Services
```bash
docker compose down
```

---

## 5. Security & Concurrency Controls

### API Security & CORS Policy
- **No Wildcard Credentials:** The backend strictly forbids `allow_credentials=True` when `CORS_ORIGINS="*"` to prevent cross-origin credential harvesting. If detected, `allow_credentials` is coerced to `False`.
- **Security Response Headers:** All responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy`.
- **Payload Limiting:** Payloads larger than 10MB are rejected with HTTP 413 to prevent memory exhaustion attacks.
- **Log Redaction:** `SensitiveDataFilter` automatically strips emails, bearer tokens, and API credentials from all console and file logs.

### SQLite Concurrency & WAL Mode
To support concurrent queries between the FastAPI multi-worker backend and the Streamlit UI:
- **Write-Ahead Logging (WAL):** Enabled via `PRAGMA journal_mode = WAL;`. Readers do not block writers, and writers do not block readers.
- **Busy Timeout:** Configured to 30,000 ms (`PRAGMA busy_timeout = 30000;`) to prevent `sqlite3.OperationalError: database is locked` during concurrent batch evaluations.
- **Transaction Atomicity:** All writes execute inside contextual rollback blocks (`try...except rollback`).

---

## 6. Deployment Smoke Testing Suite

Finova AI includes an automated deployment smoke test runner (`evaluation/deployment_smoke_tests.py`) to validate environments before release.

### Running Smoke Tests

```powershell
# Validate static configuration, files, and Dockerfiles
python evaluation/deployment_smoke_tests.py --mode static

# Validate local running services (FastAPI & Streamlit)
python evaluation/deployment_smoke_tests.py --mode local

# Validate Docker container configuration
python evaluation/deployment_smoke_tests.py --mode docker

# Comprehensive validation (all suites)
python evaluation/deployment_smoke_tests.py --mode all
```

---

## 7. Troubleshooting Guide

### 1. Frontend Cannot Connect to Backend
- **Symptom:** Streamlit UI displays `"Backend Offline / Degraded"`.
- **Cause:** `BACKEND_API_URL` is pointing to the wrong host or port.
- **Solution:**
  - Local mode: Ensure `BACKEND_API_URL=http://127.0.0.1:8000/api/v1`.
  - Docker mode: Ensure `BACKEND_API_URL=http://backend:8000/api/v1`.
  - Slashes: The resolver automatically normalizes trailing slashes and prevents duplicate `/api/v1` segments.

### 2. SEC EDGAR Returns 403 Forbidden
- **Symptom:** `SECAuthenticationError: 403 Forbidden` during filing ingestion.
- **Cause:** `SEC_USER_AGENT` contains a placeholder like `contact@example.com` or invalid format.
- **Solution:** Update `.env` with a compliant string: `AppName/1.0 (admin@verifieddomain.com)`.

### 3. Database Locked (`sqlite3.OperationalError: database is locked`)
- **Symptom:** Errors when concurrent requests write to SQLite.
- **Cause:** WAL mode disabled or timeout too short.
- **Solution:** Ensure `DATABASE_WAL_MODE=true` and `DATABASE_BUSY_TIMEOUT_MS=30000` in `.env`.

### 4. Ollama LLM Unavailable
- **Symptom:** Backend log: `LLM inference failed: Connection refused`.
- **Behavior:** Finova AI automatically falls back to deterministic rule-based answer synthesis. The application remains fully functional with zero crashes.
- **Solution:** Ensure Ollama is running (`ollama serve`) and model is pulled (`ollama pull qwen2.5:1.5b`).
