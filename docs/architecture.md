# Finova AI — System Architecture Specification

## 1. Architectural Vision

Finova AI is a modular, multi-agent financial research and intelligence system engineered to extract, verify, analyze, and synthesize corporate financial disclosures from SEC EDGAR filings (e.g., Form 10-K and 10-Q).

The primary architectural challenge addressed by Finova AI is **eliminating financial hallucinations** in AI-generated research. By decomposing financial inquiry into deterministic retrieval, specialized analytical reasoning, isolated arithmetic computation, and rigorous cross-verification, Finova AI produces audit-ready financial intelligence backed by primary source citations.

---

## 2. Multi-Agent Topology & State Graph

Finova AI utilizes a **LangGraph state machine** coordinated by a central supervisor with bidirectional verification loops.

```mermaid
flowchart TD
    User(["User Query / Ticker"]) --> Supervisor["Supervisor Agent"]
    
    subgraph MultiAgentCore ["LangGraph Orchestration Core"]
        Supervisor -->|Plan & Route| ResearchAgent["Research Agent<br/>SEC EDGAR Retrieval"]
        ResearchAgent -->|Filings & Footnotes| HybridRAG["Hybrid Retrieval Engine<br/>BM25 + Dense Embeddings"]
        HybridRAG -->|Context Chunks| AnalystAgent["Financial Analyst Agent<br/>Domain Interpretation"]
        
        AnalystAgent -->|Calculations Needed| CalcAgent["Calculation Agent<br/>Deterministic Math Engine"]
        CalcAgent -->|Verified Numbers| AnalystAgent
        
        AnalystAgent -->|Draft Findings| VerifierAgent["Verification Agent<br/>Source Fact-Checker"]
        
        VerifierAgent -->|Audit Passed| ReportAgent["Report Agent<br/>Synthesis & Formatting"]
        VerifierAgent -->|Discrepancy Detected| Supervisor
    end
    
    ReportAgent --> UserReport(["Audit-Ready Financial Report<br/>with Inline Citations"])
```

---

## 3. Agent Roster & Functional Responsibilities

| Agent Name | Architectural Role | Core Responsibilities | Execution Type |
| :--- | :--- | :--- | :--- |
| **Supervisor Agent** | Graph Coordinator | Deconstructs complex financial queries into analytical steps, maintains the shared state, routes tasks, and manages replanning if validation fails. | LLM (Reasoning) |
| **Research Agent** | SEC & Filing Specialist | Fetches company filings via SEC EDGAR API, normalizes XBRL data, extracts financial statements, and performs hybrid RAG searches over filing text/footnotes. | Tool-based + LLM |
| **Financial Analyst Agent** | Domain Analyst | Evaluates financial health, identifies trends, conducts DuPont analysis, assesses liquidity/solvency risks, and contextualizes management disclosures. | LLM (Financial Prompt) |
| **Calculation Agent** | Arithmetic Engine | Executes pure deterministic Python math (growth rates, margins, coverage ratios, WACC, DCF). **Never relies on LLMs for arithmetic.** | Deterministic Code |
| **Verification Agent** | Quality Auditor | Audits every assertion, table cell, and ratio in the draft output against the raw filing excerpt. Flags ungrounded statements or discrepancies. | Deterministic + LLM Guard |
| **Report Agent** | Synthesis Specialist | Compiles verified metrics, interpretations, and filing citations into structured Markdown/PDF research reports. | LLM (Formatting) |

---

## 4. End-to-End Processing Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Sup as Supervisor Agent
    participant Res as Research Agent
    participant Ana as Analyst Agent
    participant Calc as Calculation Agent
    participant Ver as Verification Agent
    participant Rep as Report Agent

    User->>Sup: "Compare Apple & Microsoft FCF margin expansion (2022-2024)"
    Sup->>Res: Fetch 10-K filings for AAPL and MSFT (2022-2024)
    Res-->>Sup: Structured Financial Statements & Cash Flow Footnotes
    Sup->>Calc: Compute Operating Cash Flow, Capex, and FCF Margin
    Calc-->>Sup: Deterministic calculation results with formula trace
    Sup->>Ana: Interpret capital expenditure trends & cloud investments
    Ana-->>Sup: Synthesized analytical draft
    Sup->>Ver: Audit draft against primary filing sources
    alt Citations verified & numbers match
        Ver-->>Sup: Verification APPROVED
        Sup->>Rep: Generate final comparative research brief
        Rep-->>User: Structured Report with filing citations
    else Verification failure / discrepancy
        Ver-->>Sup: Discrepancy detected (e.g. Capex footnote adjustment)
        Sup->>Res: Targeted re-query for specific filing footnote
    end
```

---

## 5. Subsystem Architecture

### 5.1 Data Ingestion & SEC EDGAR Integration (Planned: Session 02)
- **SEC EDGAR API Client**: Compliant rate-limited requests (< 10 requests/sec) using declared `User-Agent`.
- **XBRL & HTML Parsers**: Extraction of Consolidated Statements of Operations, Balance Sheets, and Cash Flows.
- **Local Cache**: Local SQLite/file caching to eliminate duplicate network calls and support offline development.

### 5.2 Hybrid Retrieval Engine (Planned: Session 03)
- **Document Chunking**: Section-aware hierarchical chunking respecting SEC filing Item boundaries (Item 1A Risk Factors, Item 7 MD&A, Item 8 Financial Statements).
- **BM25 Sparse Retrieval**: Exact keyword and financial metric code matching.
- **Dense Vector Retrieval**: Local CPU-compatible embeddings (e.g., `all-MiniLM-L6-v2` or `bge-small-en-v1.5`).
- **Reciprocal Rank Fusion (RRF)**: Merges sparse and dense search rankings for high-precision retrieval over numerical tables.

### 5.3 Deterministic Financial Engine (Planned: Session 04)
- Dedicated mathematical modules implementing standard financial formulas:
  - Profitability: Gross Margin, Operating Margin, Net Margin, ROE, ROIC.
  - Liquidity & Solvency: Current Ratio, Quick Ratio, Debt-to-Equity, Interest Coverage.
  - Cash Flow: Free Cash Flow (Operating Cash Flow - Capex), FCF Conversion Rate.
  - Multi-Year Dynamics: YoY Growth, CAGR (Compound Annual Growth Rate).
- Every calculation produces an execution receipt containing: input values, filing line-item identifiers, formula string, and final value.

### 5.4 Verification Protocol (Planned: Session 05)
- Every quantitative metric must cite an exact filing document, page, and table coordinate.
- The Verification Agent parses each claim and asserts:
  $$\text{Claimed Value} = \text{Source Coordinate Value} \pm \epsilon$$
- If a numerical assertion cannot be corroborated from the ground-truth filing excerpt, it is purged before report generation.

---

## 6. Implementation Status Matrix

| Component / Subsystem | Target Session | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Directory & Package Scaffolding** | Session 01 | **IMPLEMENTED** | Modular layout with separated concerns. |
| **Central Settings (Pydantic)** | Session 01 | **IMPLEMENTED** | Environment-driven config, `.env.example`. |
| **Centralized Logging System** | Session 01 | **IMPLEMENTED** | Console + Rotating File logs in `logs/`. |
| **FastAPI Backend Core** | Session 01 | **IMPLEMENTED** | `/health`, `/api/v1/health`, Swagger docs. |
| **Streamlit Frontend Foundation** | Session 01 | **IMPLEMENTED** | Dark navy analytics theme, status indicator. |
| **Automated Test Suite** | Session 01 | **IMPLEMENTED** | Pytest unit and integration tests. |
| **SEC EDGAR Data Ingestion** | Session 02 | Planned | Rate limiter, CIK mapper, 10-K/10-Q parser. |
| **Document Processing & Chunking** | Session 03 | Planned | Item-based SEC filing chunker. |
| **Hybrid RAG (BM25 + Vector)** | Session 03 | Planned | Local CPU embedding pipeline. |
| **Deterministic Finance Engine** | Session 04 | Planned | Financial formula library & verification receipts. |
| **LangGraph Agent Orchestration** | Session 05 | Planned | 6-agent cooperative state machine. |
| **Verification & Anti-Hallucination** | Session 05 | Planned | Citation auditing and numerical reconciliation. |
| **Full Report Generation UI** | Session 06 | Planned | Interactive dashboards, PDF export. |

---

## 7. Resource & Hardware Budget

To ensure full reproducibility without specialized cloud services or GPU hardware:
- **Compute**: Pure CPU execution on 16 GB RAM (compatible with standard Windows machines).
- **Embeddings**: Lightweight ONNX/PyTorch models (memory footprint < 500 MB).
- **LLM Strategy**: Compatible with local quantized models (via Ollama) or standard API endpoints.
- **Storage**: Local SQLite database and local disk file caching. Zero cost.

