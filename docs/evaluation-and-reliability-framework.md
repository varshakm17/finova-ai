# Finova AI — End-to-End Evaluation, Financial Accuracy & Reliability Framework

## 1. Overview & Architectural Principles

Finova AI is a deterministic, multi-agent financial research and intelligence system engineered to eliminate hallucination in corporate financial analysis. 

The **Evaluation & Reliability Framework** (Session 12) provides rigorous, offline, auditable benchmarking across four foundational system layers:
1. **Information Retrieval (IR)**: Multi-modal lexical, semantic, hybrid (Reciprocal Rank Fusion), and cross-encoder reranked retrieval across statutory SEC Form 10-K sections.
2. **Pure Financial Arithmetic**: Deterministic, pure Python calculations for profitability margins, financial liquidity, solvency, return on capital, and cash flow dynamics with zero LLM arithmetic.
3. **Anti-Hallucination & Claim Verification**: Atomic assertion extraction and deterministic claim-to-evidence auditing enforcing exact numerical tolerances, reporting period consistency, cross-evidence contradiction detection, and company attribution verification.
4. **Autonomous Multi-Section Reports**: End-to-end evaluation of multi-agent research briefs ensuring coverage across all 8 canonical sections, statutory citations, structured financial tables, and explicit limitation disclosures.

---

## 2. Benchmark Datasets (`evaluation/datasets/`)

The framework relies on four curated, reproducible offline benchmark datasets adhering strictly to authentic SEC statutory filings and controlled synthetic edge fixtures.

| Dataset Name | File Path | Scope & Format | Provenance Category |
| :--- | :--- | :--- | :--- |
| **Retrieval Benchmark** | `evaluation/datasets/retrieval_benchmark.json` | 16 multi-company queries across AAPL, MSFT, TSLA, NVDA spanning 8 categories (Overview, Revenue, Margins, Cash Flow, Risks, MD&A, Comparison). | Curated SEC Disclosures & Unannotated Reference Probes |
| **Financial Calculation Benchmark** | `evaluation/datasets/financial_calculation_benchmark.json` | 18 exhaustive calculation test cases across 10 canonical metrics covering normal calculations, zero denominators, missing inputs, negative values, and non-calendar periods. | Verified SEC XBRL Inputs & Synthetic Mathematical Fixtures |
| **Claim Verification Benchmark** | `evaluation/datasets/verification_benchmark.json` | 18 controlled probes evaluating exact numerical matches, paraphrases, missing periods, ungrounded claims, directional contradictions, scale errors, and cross-company attributions. | Curated SEC Ground Truth & Synthetic Verification Probes |
| **Report Generation Benchmark** | `evaluation/datasets/report_benchmark.json` | 8 comprehensive scenarios evaluating 8 canonical sections, citation depth, financial tables, missing debt metrics, and speculative forecast handling. | Multi-Agent Research Scenarios & Provenance Checks |

---

## 3. Core Evaluation Metrics & Formulas

### 3.1 Information Retrieval Metrics
- **Precision@K**:
  $$\text{Precision}@K = \frac{|\text{Retrieved}_K \cap \text{Relevant}|}{K}$$
- **Recall@K**:
  $$\text{Recall}@K = \frac{|\text{Retrieved}_K \cap \text{Relevant}|}{|\text{Relevant}|}$$
- **Mean Reciprocal Rank (MRR)**:
  $$\text{MRR} = \frac{1}{|Q|} \sum_{q=1}^{|Q|} \frac{1}{\text{rank}_q}$$
  where $\text{rank}_q$ is the rank position of the first relevant chunk for query $q$ (0 if no hit in retrieved set).
- **Mean Average Precision (MAP)**:
  $$\text{MAP} = \frac{1}{|Q|} \sum_{q=1}^{|Q|} \text{AP}(q), \quad \text{AP}(q) = \frac{1}{|R_q|} \sum_{k=1}^K P@k \cdot \text{rel}(k)$$
  *Note*: If $|R_q| = 0$ (unannotated query probe), $\text{AP}(q) = 0.0$ and is tracked explicitly to distinguish unannotated test probes from ranking misses.
- **Normalized Discounted Cumulative Gain (NDCG@K)**:
  $$\text{DCG}@K = \sum_{i=1}^K \frac{2^{\text{rel}_i} - 1}{\log_2(i + 1)}, \quad \text{NDCG}@K = \frac{\text{DCG}@K}{\text{IDCG}@K}$$

### 3.2 Anti-Hallucination & Verification Compliance
In financial research systems, **False Acceptance (FAR)** carries severe compliance and legal risks (accepting a fabricated, ungrounded, or contradicted claim into an investment or credit analysis).
- **True Positive (TP)**: Verified grounded claim correctly classified as supported.
- **False Positive (FP / False Acceptance)**: Ungrounded or contradicted claim erroneously accepted as supported.
- **True Negative (TN)**: Ungrounded or contradicted claim correctly rejected or marked unsupported.
- **False Negative (FN / False Rejection)**: Verified grounded claim erroneously rejected or marked unsupported.
- **False Acceptance Rate (FAR)**:
  $$\text{FAR} = \frac{\text{FP}}{\text{FP} + \text{TN}}$$
- **False Rejection Rate (FRR)**:
  $$\text{FRR} = \frac{\text{FN}}{\text{TP} + \text{FN}}$$
- **Precision**: $\frac{\text{TP}}{\text{TP} + \text{FP}}$
- **Recall**: $\frac{\text{TP}}{\text{TP} + \text{FN}}$

### 3.3 Financial Arithmetic Accuracy
- **Zero-Denominator Defense**: In ratios where the statutory denominator is zero (e.g. revenue = 0 for profit margins, current liabilities = 0 for liquidity), the engine assigns `status="unavailable"` and `value=None`. The system **never silently converts zero denominators to zero**.
- **Mean Absolute Error (MAE)**:
  $$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |\text{Actual}_i - \text{Expected}_i|$$
- **CapEx Sign Convention**: Free Cash Flow enforces explicit normalization of capital expenditures:
  $$\text{FCF} = \text{Operating Cash Flow} - |\text{Capital Expenditures}|$$

---

## 4. Evaluator Modules (`evaluation/`)

1. `evaluation/financial_evaluator.py`: Pure Python arithmetic auditor testing all 10 canonical metrics, MAE calculation, and zero-denominator resilience.
2. `evaluation/verification_evaluator.py`: Anti-hallucination verification auditor testing exact number match, period consistency, contradiction detection, and company attribution.
3. `evaluation/retrieval_evaluator.py`: Unified search auditor evaluating dense, sparse, hybrid, and reranked search quality.
4. `evaluation/report_evaluator.py`: End-to-end report generator evaluator enforcing 8 canonical sections, table presence, citations, and limitation compliance.

---

## 5. Command-Line Runner (`evaluation/run_evaluation.py`)

Run benchmark suites directly from terminal:

```bash
# Run all benchmark suites
python -m evaluation.run_evaluation --eval-type all

# Run financial arithmetic benchmark
python -m evaluation.run_evaluation --eval-type financial_calculation

# Run anti-hallucination verification benchmark
python -m evaluation.run_evaluation --eval-type verification

# Run retrieval benchmark with Top-K cutoff and mode
python -m evaluation.run_evaluation --eval-type retrieval --top-k 5 --retrieval-mode hybrid

# Run autonomous report quality benchmark
python -m evaluation.run_evaluation --eval-type report
```

---

## 6. REST API Endpoints (`/api/v1/evaluations`)

- `POST /api/v1/evaluations/run`: Trigger benchmark run with request body `EvaluationRunRequest`.
- `GET /api/v1/evaluations/{run_id}`: Retrieve run scorecards, summary, metrics, and recorded issues.
- `GET /api/v1/evaluations`: List historical benchmark executions with optional `eval_type` and `limit`.
- `GET /api/v1/evaluations/{run_id}/cases`: Retrieve per-case outcomes and diagnostics with optional `passed` filter.
- `GET /api/v1/evaluations/benchmarks`: Retrieve metadata and catalogs for available offline datasets.

---

## 7. Production Hardening & Security Measures

- **Input Boundary Hardening**: Questions submitted to `/rag/ask`, `/agents/run`, and `/reports/generate` enforce strict `max_length=2000` boundaries, rejecting oversized buffer payloads with HTTP 422.
- **Directory Traversal Protection**: Benchmark dataset paths are validated to ensure no unauthorized filesystem traversal.
- **Parameterized SQL**: All SQLite database queries in `backend/data/storage.py` utilize parameterized `?` binds.
- **XSS Prevention in HTML Reports**: All dynamically rendered strings (`company_name`, `ticker`, `period`) are escaped via `html.escape`.
- **Zero-Budget Offline Independence**: Zero live network calls to SEC EDGAR or external LLM APIs are required for tests and benchmarks.

