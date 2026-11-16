# Autonomous Financial Research Briefs & Multi-Section Report Generation (Session 11)

## 1. Executive Summary

Finova AI Session 11 extends the multi-agent system from single-turn question answering into an **Autonomous Financial Research and Intelligence Brief Engine**. The system autonomously accepts high-level financial research objectives (e.g., *"Analyze Microsoft's financial performance, profitability margins, revenue growth trends, and core risk factors across the last three fiscal years"*), decomposes them into specialized research tasks, executes structured SEC EDGAR retrieval across statutory filings, computes longitudinal multi-period financial trends using deterministic Python formulas (guaranteed zero LLM arithmetic), reconciles narrative and computational evidence, synthesizes multi-section research briefs in GitHub Flavored Markdown and publication-ready HTML, and verifies every asserted figure with claim-level anti-hallucination audits.

---

## 2. Architecture & LangGraph Workflow

The report generation workflow (`FINANCIAL_RESEARCH_REPORT`) introduces three specialized agents into the LangGraph StateGraph topology alongside the existing Supervisor, Research, Financial Analyst, and Verification agents:

```
[START]
   │
   ▼
[SupervisorAgent]
   │ (Intent: REPORT_GENERATION / Workflow: FINANCIAL_RESEARCH_REPORT)
   ▼
[ResearchPlanner]
   │ (Deconstructs objective into ordered tasks: 10-K retrieval, metrics, trends, MD&A, risks)
   ▼
[ResearchAgent]
   │ (Executes multi-task hybrid search and Cross-Encoder reranking over SEC filing chunks)
   ▼
[FinancialAnalystAgent]
   │ (Calculates multi-period XBRL metrics, percentage changes, and directional trends)
   ▼
[ResearchCoordinator]
   │ (Maps citations [E1], [C1], groups findings: calculated, narrative, confirmed, unresolved)
   ▼
[ReportAgent]
   │ (Assembles multi-section brief with comparative tables in Markdown and semantic HTML)
   ▼
[VerificationAgent]
   │ (Audits numbers and claims against receipts and evidence)
   ├── Status == REJECTED / Invalid ──► [SafeResponse] ──► [END]
   └── Status in (VERIFIED, WARNINGS) ─────────────────► [END]
```

---

## 3. Core Components

### 3.1 Research Planner (`backend/agents/research_planner.py`)
- **Deterministic Task Decomposition**: Analyzes inquiries for target companies, multi-year periods (`FY2021`, `FY2022`, `FY2023`, *"last 3 years"*), and required financial metrics.
- **Ordered Task Plan**: Generates typed `ResearchTask` items covering:
  - `FILING_RETRIEVAL`: Disclosures across statutory 10-K sections (Item 1, Item 7, Item 1A).
  - `METRIC_CALCULATION`: Profitability, liquidity, leverage, and cash flow formulas.
  - `TREND_ANALYSIS`: Period-over-period delta and longitudinal trajectory computation.
  - `MDA_ANALYSIS`: Operational drivers and management commentary.
  - `RISK_ANALYSIS`: Statutory risk factor evaluation.
  - `SYNTHESIS`: Executive assembly.
  - `VERIFICATION`: Factual claim and numeric audit.
- **Plan Validation**: Guarantees all target tickers, fiscal periods, and executable tasks are valid before dispatching execution.

### 3.2 Longitudinal Trend Calculation (`backend/agents/financial_analyst_agent.py`)
- **Guaranteed Zero LLM Arithmetic**: All ratios, absolute deltas, and percentage changes are computed strictly in Python.
- **Deterministic Formulas**:
  $$\text{Absolute Change} = V_{\text{final}} - V_{\text{base}}$$
  $$\text{Percentage Change} = \frac{V_{\text{final}} - V_{\text{base}}}{|V_{\text{base}}|} \times 100 \quad (\text{for } |V_{\text{base}}| > 0)$$
- **Trajectory Classification**:
  - `UPWARD`: Monotonically increasing across comparative periods.
  - `DOWNWARD`: Monotonically decreasing across comparative periods.
  - `FLAT`: Absolute change within $\pm 0.0001$.
  - `MIXED`: Fluctuating across multiple periods.
- **Financial Semantics**: Contextual interpretation accounts for metric meaning (e.g., expanding profitability vs increasing debt leverage vs tightening liquidity).

### 3.3 Research Coordinator (`backend/agents/research_coordinator.py`)
- **Auditable Citation Indexing**: Maps text disclosures to `[E1]`, `[E2]`, etc., and deterministic calculation receipts to `[C1]`, `[C2]`, etc.
- **Evidence Reconciliation**: Organizes findings into four categories:
  - `calculated`: Facts derived strictly from verified Python calculation receipts.
  - `narrative`: Qualitative disclosures and operational insights from Item 1, 1A, and 7.
  - `confirmed`: Trajectories where calculation receipts and narrative reinforce each other.
  - `unresolved`: Documented gaps, missing XBRL observations, or filing warnings.

### 3.4 Report Generation Agent (`backend/agents/report_agent.py`)
- **Canonical Multi-Section Structure**:
  1. Executive Summary & Research Scope
  2. Company Overview & Business Architecture
  3. Financial Performance & Key Ratios (with structured markdown/HTML table)
  4. Historical Multi-Period Comparison & Trends (comparative delta and % change table)
  5. Business Operations & MD&A Disclosures
  6. Risk Factors & Strategic Uncertainties
  7. Key Findings & Strategic Takeaways
  8. Sources & Statutory SEC References (accession numbers, form types, filing dates, SEC URLs)
- **Publication-Ready Semantic HTML**: Self-contained executive briefing design with responsive typography, financial navy styling (`#1e3a8a`), verification status badges, and styled data tables.

### 3.5 Anti-Hallucination Verification Integration (`backend/agents/verification_agent.py`)
- Every generated section and comparative figure is audited against cited calculation receipts and retrieved filing excerpts.
- Discrepancies or contradictory claims automatically flag `report.status = "REJECTED"` and withhold ungrounded responses from production delivery.

---

## 4. SQLite Persistence Schema

Four relational tables persist research deliverables and provenance in `finova.db`:

1. `research_plans`: Stores `plan_id`, `request_id`, `company_name`, `ticker`, `objective`, `reporting_period`, and full `plan_json`.
2. `financial_research_reports`: Stores `report_id`, `request_id`, `plan_id`, `ticker`, `company_name`, `title`, `reporting_period`, `status`, `verification_status`, `markdown_content`, `html_content`, and section/evidence counters.
3. `report_sections`: Stores `section_id`, `report_id`, `section_key`, `title`, `order_index`, `content_markdown`, `evidence_ids_json`, `calculation_ids_json`, and section `verification_status`.
4. `report_references`: Stores `reference_id`, `report_id`, `ref_type`, `citation_id`, `filing_name`, `form_type`, `filing_date`, `reporting_period`, `accession_number`, and `sec_url`.

---

## 5. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/reports/generate` | Initiates autonomous research planning, task retrieval, trend calculation, and multi-section report assembly. |
| `GET` | `/api/v1/reports/{report_id}` | Retrieves a complete stored research report with all sections and statutory references. |
| `GET` | `/api/v1/reports/{report_id}/verification` | Retrieves claim-level verification audits and evidence quality scores for a report. |
| `GET` | `/api/v1/reports` | Lists historical reports with optional `ticker` filter and pagination. |

---

## 6. Streamlit Workspace

The interactive frontend (`frontend/app.py`) provides an **Autonomous Research Reports** workspace:
- Research brief objective submission form with target ticker, period, and format selection (Markdown or HTML).
- Progress indicator detailing plan deconstruction and agent execution trace.
- Interactive multi-period financial tables and directional trend indicators.
- Live tabbed viewer with Markdown view, rendered HTML preview (`components.html`), verification scorecard, and one-click download buttons (`.md` and `.html`).
- Historical report browser allowing users to inspect and reload past deliverables.
