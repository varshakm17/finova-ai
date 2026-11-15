# Finova AI — Multi-Agent Financial Research and Intelligence System

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3119/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.38+-FF4B4B.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Session 03 Ingestion Complete](https://img.shields.io/badge/Status-Filing%20Ingestion%20Active-brightgreen.svg)]()
[![Tests: 75 Passed](https://img.shields.io/badge/Tests-75%20Passed%20(87%25%20cov)-brightgreen.svg)]()

Finova AI is a modular, production-oriented financial intelligence platform designed to extract, compute, cross-verify, and synthesize evidence-backed corporate financial research from SEC EDGAR company filings (Forms 10-K and 10-Q).

---

## 1. Problem Statement

Financial research requires analyzing hundreds of pages of complex statutory disclosures, footnotes, and balance sheets. Traditional LLM-based solutions suffer from severe vulnerabilities in financial contexts:
- **Hallucinated figures**: Fabricating financial numbers or confusing quarterly with annual results.
- **Arithmetic errors**: Inaccurate financial ratios, margins, and compound growth calculations.
- **Untraceable assertions**: Presenting quantitative insights without exact filing coordinates or citations.
- **Information obsolescence**: Inability to systematically trace multi-year performance across changing accounting standards.

Finova AI solves these limitations through an orchestrated multi-agent architecture where retrieval, arithmetic calculation, domain analysis, and source verification are rigorously segregated.

---

## 2. Project Objectives

- **Automated Filing Retrieval**: Directly fetch primary annual (10-K) and quarterly (10-Q) filings from the SEC EDGAR system.
- **Deterministic Metric Extraction**: Parse structured financial statements (Operations, Balance Sheets, Cash Flows) with XBRL tagging.
- **Document Preprocessing & Section Extraction**: Extract clean, readable text from HTML/inline XBRL filings, isolate core sections (Item 1, 1A, 7, 7A), and bypass Table of Contents false-positives.
- **Section-Aware Chunking**: Segment narrative disclosures into boundary-aware, overlapping chunks preserving full filing provenance and character coordinates.
- **Pure Arithmetic Calculation**: Compute growth rates, profitability margins, liquidity metrics, and valuation ratios using verified deterministic code rather than LLM text generation.
- **Longitudinal & Cross-Company Benchmarking**: Compare financial performance across multiple fiscal years and industry peers.
- **Hybrid RAG for Qualitative Footnotes**: Query risk factors (Item 1A) and Management Discussion & Analysis (Item 7) with dense and sparse vector retrieval.
- **Anti-Hallucination Verification**: Cross-verify every numerical statement against the underlying SEC disclosure prior to report generation.
- **Evidence-Backed Reporting**: Produce comprehensive research briefs complete with page references and line-item coordinates.

---

## 3. Major Features

1. **SEC EDGAR Client Engine**: Compliant rate-limited ingestion of SEC company facts and full-text filings with automatic backoff retries.
2. **Company Identification & Ticker Resolution**: In-memory and disk-cached CIK resolution from master SEC directory.
3. **XBRL Metric Extraction & Temporal Normalization**: Section-aware parsing that separates Annual, Standalone Quarterly, Year-To-Date (YTD), and Point-in-Time Instant values.
4. **Statutory Document Ingestion Pipeline**: Compliant downloading and local caching of primary 10-K and 10-Q HTML documents with domain whitelisting and SHA-256 integrity checks.
5. **HTML & Inline XBRL Normalization**: BeautifulSoup parser stripping scripts, styles, comments, and hidden trackers while unwrapping inline XBRL tags and formatting tables into pipe-separated structures.
6. **Heuristic Section Extraction**: Identifies and extracts canonical Items 1, 1A, 7, and 7A across Form 10-K and 10-Q structures while rejecting Table of Contents false-positives.
7. **Section-Aware Chunking Engine**: Generates ~3,500-char chunks (~400 overlap) snapping cleanly to paragraph or sentence boundaries with full citation metadata.
8. **Relational SQLite Store**: Foreign-key backed persistence layer for companies, filings, financial observations, documents, sections, and chunks.
9. **Interactive Streamlit Workspace**: Multi-view dashboard for company lookup, filing metadata, numerical metric exploration, and document ingestion/chunk inspection.
10. **Deterministic Financial Math Library**: *(Planned: Session 04)* Calculation receipts ensuring zero arithmetic errors.
11. **Multi-Agent Orchestration Graph (LangGraph)**: *(Planned: Session 05)* 6-agent cooperative state machine.

---

## 4. Technology Stack

- **Runtime & Language**: Python 3.11
- **Backend Framework**: FastAPI (Asynchronous REST API, OpenAPI/Swagger)
- **Frontend Framework**: Streamlit (Interactive Financial Analytics Dashboard)
- **Document Processing**: BeautifulSoup4 (Standard zero-C html.parser)
- **Configuration Management**: Pydantic Settings (Environment-driven configuration)
- **Data & Computation**: Pandas, NumPy
- **HTTP & Networking**: Requests, HTTPX
- **Testing & Quality**: Pytest, Pytest-cov, Ruff
- **Database**: SQLite with foreign keys enabled (Zero external infrastructure dependency)
- **Execution Target**: Standard CPU execution (16 GB RAM, no GPU required)
- **Planned Orchestration**: LangGraph, Local Embeddings, Hybrid BM25

---

## 5. System Architecture Overview

```mermaid
flowchart LR
    A["User Query"] --> B["Supervisor Agent"]
    B --> C["Research Agent<br/>SEC EDGAR"]
    C --> D["Analyst Agent"]
    D <--> E["Calculation Agent<br/>Deterministic Math"]
    D --> F["Verification Agent<br/>Source Fact-Checker"]
    F --> G["Report Agent<br/>Synthesis"]
    G --> H["Evidence-Backed Report"]
```

For detailed architectural specifications, agent definitions, sequence diagrams, and data ingestion workflows:
- [architecture.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Finova%20AI/docs/architecture.md) — Multi-agent system topology.
- [sec-data-pipeline.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Finova%20AI/docs/sec-data-pipeline.md) — Numerical XBRL ingestion pipeline and schema specification.
- [filing-ingestion.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Finova%20AI/docs/filing-ingestion.md) — Document downloading, HTML parsing, section extraction, and chunking specification.

---

## 6. Repository Structure

```
finova-ai/
│
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application factory and entrypoint
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # REST API endpoints (Health, Companies, Ingestion, Chunks)
│   ├── data/                   # SEC EDGAR ingestion, document processing, and storage
│   │   ├── __init__.py
│   │   ├── sec_client.py       # Rate-limited SEC EDGAR HTTP client with backoff
│   │   ├── company_service.py  # Ticker-to-CIK resolution and caching
│   │   ├── filing_downloader.py # Secure SEC document downloader with file caching
│   │   ├── html_parser.py      # HTML/inline-XBRL parser and table formatter
│   │   ├── section_extractor.py # 10-K / 10-Q section isolation and TOC filter
│   │   ├── chunker.py          # Boundary-aware, section-aware text chunker
│   │   ├── document_storage.py # SQLite storage engine for documents, sections, chunks
│   │   ├── filing_ingestion_service.py # Orchestrator for end-to-end filing ingestion
│   │   ├── financial_extractor.py # XBRL company facts parser & US-GAAP mapper
│   │   ├── data_normalizer.py  # Observation schema and period classification
│   │   └── storage.py          # SQLite relational database engine
│   ├── agents/                 # (Session 05) Multi-agent implementations
│   │   └── __init__.py
│   ├── graph/                  # (Session 05) LangGraph state graphs
│   │   └── __init__.py
│   ├── retrieval/              # (Session 04/05) Hybrid RAG retrieval pipelines
│   │   └── __init__.py
│   ├── finance/                # (Session 04) Deterministic financial calculation
│   │   └── __init__.py
│   ├── evaluation/             # (Session 06) Benchmarks and quality metrics
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       └── logger.py           # Centralized console and rotating file logger
│
├── frontend/
│   ├── __init__.py
│   └── app.py                  # Streamlit application with ingestion and chunk viewer
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic Settings configuration loader
│
├── datasets/
│   ├── README.md               # Guidelines for raw filing storage and cache
│   ├── cache/                  # Local cache for SEC ticker directory
│   └── filings/                # Local cache for downloaded SEC HTML filings (git-ignored)
│
├── notebooks/
│   └── .gitkeep                # Exploratory analysis scratchpads
│
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── sec_mock_data.py    # Mock SEC submissions and facts payloads
│   │   └── sec_html_fixtures.py # Mock 10-K, 10-Q, and inline-XBRL HTML fixtures
│   ├── test_health.py          # Foundation & health check tests
│   ├── test_sec_client.py      # SECClient, CIK, and User-Agent validation tests
│   ├── test_company_service.py # Company lookup and caching tests
│   ├── test_financial_extractor.py # XBRL extraction & period typing tests
│   ├── test_storage.py         # SQLite persistence, foreign keys, & upsert tests
│   ├── test_api_endpoints.py   # FastAPI company & financial endpoint tests
│   ├── test_filing_downloader.py # Download validation, caching, and host checks
│   ├── test_html_parser.py     # HTML cleaning, inline XBRL, and table format tests
│   ├── test_section_extractor.py # 10-K/10-Q section boundaries and TOC rejection tests
│   ├── test_chunker.py         # Boundary alignment, overlap, and deterministic tests
│   ├── test_document_storage.py # Document, section, and chunk persistence tests
│   ├── test_filing_ingestion_service.py # End-to-end ingestion pipeline tests
│   └── test_api_ingestion_endpoints.py # FastAPI filing ingestion and chunk routes
│
├── docs/
│   ├── architecture.md         # System architecture specification
│   ├── sec-data-pipeline.md    # SEC data ingestion & retrieval specification
│   └── filing-ingestion.md     # Document ingestion, section extraction, and chunking
│
├── logs/
│   ├── .gitkeep
│   └── finova.log              # Application runtime logs
│
├── .env.example                # Environment variable template
├── .gitignore                  # Git exclusions for secrets, venvs, and filing downloads
├── requirements.txt            # Core runtime dependencies
├── requirements-dev.txt        # Development and testing dependencies
├── README.md                   # Project documentation
└── LICENSE                     # MIT License
```

---

## 7. Statutory Document Ingestion & Section-Aware Chunking

### Supported Filing Types
- **Form 10-K**: Annual reports (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 7A Market Risk).
- **Form 10-Q**: Quarterly reports (Part I Item 2 MD&A, Part I Item 3 Market Risk, Part II Item 1A Risk Factors).

### HTML Normalization & Table Formatting
- Eliminates script, style, comments, and hidden tracking snippets.
- Unrolls inline XBRL structures (`<ix:nonFraction>`, `<ix:nonNumeric>`) without losing numerical text or adding unwanted line breaks.
- Formats tabular data into clean pipe-delimited text (`Col 1 | Col 2 | Col 3`).

### Table of Contents (TOC) Traps & Heuristic Rejection
TOC listings with identical headings are rejected by evaluating character distance to the next item (`min_section_chars=150`).

### Section-Aware Chunking Strategy
- Target chunk size: **3,500 characters** with **400 character overlap**.
- Natural boundary preservation: Breaks at paragraph boundaries (`\n\n`) or sentence terminators (`. `, `! `, `? `).
- Provenance: Every chunk stores ticker, CIK, accession number, filing form, section ID, title, character offsets, and source URL.

---

## 8. REST API Endpoints & Examples

The FastAPI backend exposes interactive Swagger UI at `http://127.0.0.1:8000/docs`.

### 1. Ingest SEC Filing
- **Endpoint**: `POST /api/v1/companies/AAPL/filings/0000320193-23-000106/ingest`
- **Query Params**: `force_refresh=false`
- **Response**:
  ```json
  {
    "document_id": "0000320193_000032019323000106",
    "ticker": "AAPL",
    "cik": "0000320193",
    "company_name": "Apple Inc.",
    "accession_number": "0000320193-23-000106",
    "filing_type": "10-K",
    "filing_date": "2023-11-03",
    "report_date": "2023-09-30",
    "processing_status": "completed",
    "sections_extracted": ["ITEM_1", "ITEM_1A", "ITEM_7", "ITEM_7A"],
    "sections_not_found": [],
    "total_chunks": 14,
    "document_hash": "a4d95f8e...",
    "file_size_bytes": 1824050,
    "warnings": []
  }
  ```

### 2. List Ingested Documents
- **Endpoint**: `GET /api/v1/companies/AAPL/documents?filing_type=10-K`
- **Response**: List of previously ingested document summaries.

### 3. Get Ingested Document Details
- **Endpoint**: `GET /api/v1/companies/AAPL/documents/0000320193-23-000106`
- **Response**: Metadata, extracted section extraction statuses, character counts, and total chunks.

### 4. Retrieve Document Chunks
- **Endpoint**: `GET /api/v1/companies/AAPL/documents/0000320193-23-000106/chunks?section_identifier=ITEM_1A`
- **Response**: Section-aware chunks with full provenance and character offsets.

---

## 9. Windows Installation & Execution

### 1. Activate Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Ensure `SEC_USER_AGENT` contains a valid contact email:
```ini
SEC_USER_AGENT="FinovaAI-Research/0.1.0 (contact@example.com)"
```

### 3. Run FastAPI Backend
```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Run Streamlit Frontend
```powershell
streamlit run frontend/app.py
```

### 5. Run Automated Tests
```powershell
pytest -v --cov=backend --cov=config
```

---

## 10. Implementation Status

- [x] Standardized project repository layout with separation of concerns.
- [x] Python 3.11 virtual environment configuration.
- [x] Centralized configuration management using Pydantic Settings (`config/settings.py`).
- [x] Centralized logging system writing to console and `logs/finova.log` (`backend/utils/logger.py`).
- [x] Operational FastAPI backend with health and metadata endpoints (`backend/main.py`).
- [x] SEC EDGAR Client with User-Agent validation, rate-limiting, and backoff (`backend/data/sec_client.py`).
- [x] Company identification, ticker normalization, and disk caching (`backend/data/company_service.py`).
- [x] Financial data extraction for 17 canonical US-GAAP concepts (`backend/data/financial_extractor.py`).
- [x] Period typing distinguishing Annual, Standalone Quarter, YTD, and Instant (`backend/data/data_normalizer.py`).
- [x] Relational SQLite storage with foreign keys and unique constraints (`backend/data/storage.py`).
- [x] Secure SEC filing HTML downloader with host validation and local caching (`backend/data/filing_downloader.py`).
- [x] HTML & inline XBRL parser with table preservation and markup cleaning (`backend/data/html_parser.py`).
- [x] Section extractor for Items 1, 1A, 7, 7A across 10-K and 10-Q with TOC rejection (`backend/data/section_extractor.py`).
- [x] Boundary-aware text chunker with paragraph/sentence snapping and provenance (`backend/data/chunker.py`).
- [x] Document, section, and chunk SQLite storage engine with foreign keys (`backend/data/document_storage.py`).
- [x] End-to-end filing ingestion service orchestrator (`backend/data/filing_ingestion_service.py`).
- [x] FastAPI filing ingestion, document listing, detail, and chunk retrieval endpoints (`backend/api/routes.py`).
- [x] Streamlit filing selection, ingestion status, section breakdown, and chunk inspector UI (`frontend/app.py`).
- [x] Automated test suite with 75 unit and integration tests passing offline with 87% coverage (`tests/`).
- [x] Comprehensive documentation in `README.md`, `docs/sec-data-pipeline.md`, and `docs/filing-ingestion.md`.

---

## 11. Future Development Roadmap

- **Session 04: Deterministic Financial Calculation Engine**
  - Strict Python implementations of financial ratios and margin formulas.
  - Execution receipts with line-item traceability.
- **Session 05: Hybrid RAG & Vector Embeddings**
  - CPU-optimized local embeddings over extracted chunks.
  - BM25 + dense hybrid search with reciprocal rank fusion (RRF).
- **Session 06: LangGraph Multi-Agent Orchestration**
  - 6-agent cooperative state graph.
  - Bidirectional verification and anti-hallucination auditor.
- **Session 07: Production UI & Full Report Generation**
  - Interactive financial dashboard.
  - Exportable PDF research briefs with source citations.

---

## 12. License

Distributed under the MIT License. See [LICENSE](file:///c:/Users/LENOVO/OneDrive/Desktop/Finova%20AI/LICENSE) for more details.
