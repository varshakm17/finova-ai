# Finova AI — Retrieval Evaluation, Cross-Encoder Reranking & Evidence Quality

**Session 07 Documentation**  
**Version:** 0.1.0  
**Status:** Implemented & Verified  

---

## 1. Overview & Objectives

In Session 07, Finova AI establishes an empirical evaluation framework for its search infrastructure, an optional second-stage cross-encoder reranking layer, and a deterministic evidence-quality validation system. 

Before generative Large Language Models (LLMs) synthesize financial intelligence reports or answer multi-agent research questions, the underlying retrieval pipeline must be quantitatively benchmarked and candidate passages audited for statutory provenance, official SEC archive domain authenticity, textual duplication, and temporal reporting period consistency.

### Key Capabilities Introduced in Session 07
1. **Curated Evaluation Dataset Format**: Structured JSON schema supporting query filters (ticker, filing type, section), ground-truth chunk IDs, graded relevance scores, and metadata distinguishing synthetic fixtures from human-curated benchmarks.
2. **Deterministic IR Metrics Engine**: Hand-crafted, zero-dependency implementations of Precision@K, Recall@K, Recall@5/10/20, Mean Reciprocal Rank (MRR), Mean Average Precision (MAP), Normalized Discounted Cumulative Gain (NDCG@K), and Query Coverage, supporting both macro and micro aggregations.
3. **Multi-Retriever Comparative Benchmark**: Fair, apples-to-apples comparison of Dense Semantic Search, Sparse BM25 Search, Hybrid Reciprocal Rank Fusion (RRF), and Cross-Encoder Reranked Hybrid Search.
4. **Lightweight Cross-Encoder Reranking Layer**: CPU-compatible reranker powered by `cross-encoder/ms-marco-MiniLM-L-6-v2` with lazy loading, configurable batch inference, candidate over-fetching, provenance preservation, and complete offline fallback capability.
5. **Deterministic Evidence Quality Validator**: Statutory metadata completeness verification, approved SEC EDGAR archive domain whitelisting, SQLite document record cross-checking, exact and near-duplicate passage detection (Jaccard token similarity), and multi-period temporal mismatch detection.
6. **Query-Level Evidence Report Generator**: LLM-independent evidence briefs combining ranked passages, reranking execution receipts, validation status flags, and direct SEC EDGAR citation links.
7. **FastAPI & Streamlit Extensions**: 5 new REST API routes and a comprehensive Streamlit evaluation workspace with method comparisons, per-query inspection, reranker latency benchmarking, and evidence audits.

---

## 2. Evaluation Dataset Architecture

Evaluation queries are stored in `datasets/evaluation/retrieval_queries.json` according to the following schema:

```json
{
  "query_id": "EVAL-001",
  "query": "What are the primary supply chain and component manufacturing risks facing Apple?",
  "ticker": "AAPL",
  "filing_type": "10-K",
  "section_identifier": "ITEM_1A",
  "relevant_chunk_ids": [
    "0000320193_000032019323000106_ITEM_1A_0001",
    "0000320193_000032019323000106_ITEM_1A_0002"
  ],
  "relevance_grades": {
    "0000320193_000032019323000106_ITEM_1A_0001": 2,
    "0000320193_000032019323000106_ITEM_1A_0002": 1
  },
  "dataset_type": "synthetic",
  "notes": "Synthetic fixture targeting Item 1A Risk Factors on component manufacturing dependencies."
}
```

### Distinction Between Synthetic Fixtures and Curated Data

> [!IMPORTANT]
> **Synthetic Relevance Fixtures** (`"dataset_type": "synthetic"`) are designed exclusively for automated unit and regression testing. They verify that ranking mathematics, score sorting, cutoffs, and rank fusion logic function deterministically without requiring live SEC downloads. **Synthetic metrics do NOT demonstrate real-world financial domain retrieval efficacy.**

> [!NOTE]
> **Human-Curated Relevance Judgments** (`"dataset_type": "curated"`) represent real-world evaluation benchmarks annotated by financial domain experts inspecting actual 10-K and 10-Q filing disclosures.

---

## 3. Deterministic IR Metrics Mathematical Specification

All evaluation metrics are implemented in `backend/evaluation/retrieval_evaluator.py` without third-party evaluation dependencies:

### 1. Precision@K
Measures the proportion of retrieved documents in the top $K$ positions that are relevant:
$$\text{Precision}@K = \frac{|\text{Retrieved}_K \cap \text{Relevant}|}{K}$$
Retrieved candidate lists are deduplicated preserving initial rank before applying cutoff $K$.

### 2. Recall@K
Measures the fraction of all known relevant documents successfully retrieved in the top $K$:
$$\text{Recall}@K = \frac{|\text{Retrieved}_K \cap \text{Relevant}|}{|\text{Relevant}|}$$
If $|\text{Relevant}| = 0$, Recall is defined as $0.0$.

### 3. Mean Reciprocal Rank (MRR)
Measures how high in the ranking the first relevant document appears across a query set $Q$:
$$\text{MRR} = \frac{1}{|Q|} \sum_{q=1}^{|Q|} \frac{1}{\text{rank}_q}$$
where $\text{rank}_q$ is the 1-based rank of the first relevant retrieved document for query $q$ (or 0 if no relevant document was retrieved).

### 4. Mean Average Precision (MAP)
Calculates the mean of Average Precision (AP) across evaluable queries:
$$\text{AP} = \frac{1}{|\text{Relevant}|} \sum_{i=1}^{N} (\text{Precision}@i \times \text{rel}(i))$$
where $\text{rel}(i) = 1$ if the document at rank $i$ is relevant, and $0$ otherwise.

### 5. Normalized Discounted Cumulative Gain (NDCG@K)
Evaluates graded relevance ($rel \ge 0$) with logarithmic position discounts:
$$\text{DCG}@K = \sum_{i=1}^{\min(K, N)} \frac{2^{rel_i} - 1}{\log_2(i + 1)}$$
$$\text{IDCG}@K = \sum_{i=1}^{\min(K, |\text{Relevant}|)} \frac{2^{ideal\_rel_i} - 1}{\log_2(i + 1)}$$
$$\text{NDCG}@K = \frac{\text{DCG}@K}{\text{IDCG}@K}$$
If $\text{IDCG}@K = 0$, $\text{NDCG}@K$ is defined as $0.0$.

### 6. Macro vs. Micro Aggregation
- **Macro Averages**: Compute metrics independently per query and take the arithmetic mean across all evaluated queries. This treats all queries equally regardless of the number of ground-truth relevant chunks.
- **Micro Averages**: Aggregate total hits and denominators across the entire corpus before dividing:
  $$\text{Micro-Precision} = \frac{\sum_{q} \text{Hits}_q}{|Q| \times K}, \quad \text{Micro-Recall} = \frac{\sum_{q} \text{Hits}_q}{\sum_{q} |\text{Relevant}_q|}$$

---

## 4. Multi-Retriever Comparative Benchmark

Implemented in `backend/evaluation/retrieval_comparison.py`, `RetrievalComparator` evaluates the same evaluation queries and filters across:
1. **Dense Semantic Search**: Cosine similarity over `all-MiniLM-L6-v2` 384-dimensional FAISS/NumPy index.
2. **Sparse Lexical Search**: Okapi BM25 with financial tokenization and Lucene smoothed IDF.
3. **Hybrid RRF Search**: Reciprocal Rank Fusion blending dense and sparse candidate pools with $k=60$.
4. **Cross-Encoder Reranked Hybrid**: Lightweight second-stage reranker scoring candidate pool on CPU.

### Fair Comparison Principles
- **Identical Query Set**: Every retrieval modality executes against the exact same query text and ground truth.
- **Identical Filters**: Ticker, filing type, and section filters apply uniformly.
- **Objective Relative Deltas**: Percentage change relative to baselines:
  $$\Delta_{\text{baseline}} = \frac{\text{Metric}_{\text{hybrid}} - \text{Metric}_{\text{baseline}}}{\text{Metric}_{\text{baseline}}} \times 100\%$$
- **No False Superiority Assumption**: If sparse search outperforms hybrid on exact acronym lookups or specific numerical disclosures, the comparison transparently reports negative deltas without masking.

---

## 5. Cross-Encoder Reranking Architecture

Located in `backend/retrieval/reranker.py`, `CrossEncoderReranker` provides candidate reranking:

```
                  +-----------------------------------+
                  | Hybrid Search (RRF Constant k=60) |
                  +-----------------------------------+
                                    |
                         Candidate Pool (Top 25-50)
                                    v
                  +-----------------------------------+
                  | Cross-Encoder MiniLM-L-6-v2 (CPU) |
                  |  Pairs: (Query, Chunk Text)       |
                  |  Batch Size: 16                   |
                  +-----------------------------------+
                                    |
                       Reranked & Sorted Candidates
                                    v
                  +-----------------------------------+
                  | Top-K Results (Preserving RRF     |
                  | Dense & Sparse Provenance Ranks)  |
                  +-----------------------------------+
```

### Key Technical Attributes
- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (approx. 80MB, 22.7M parameters).
- **Execution Device**: Configured strictly for `"cpu"` inference.
- **Lazy Initialization**: Model weights are never imported or loaded during module import or standard pytest execution. Loading occurs only upon first active query when enabled.
- **Batch Processing**: Configurable `RERANKER_BATCH_SIZE=16` prevents memory spikes on 16GB consumer laptops.
- **Graceful Fallback**: If disabled (`RERANKER_ENABLED=False`) or weights cannot be accessed offline, the reranker safely returns candidates in original hybrid RRF rank order with descriptive fallback metadata without crashing.
- **Dependency Injection**: Test suites inject mock encoders for instant, deterministic, zero-network unit testing.

---

## 6. Deterministic Evidence Quality Validation

Implemented in `backend/evaluation/evidence_validator.py`, the validator analyzes candidate passages across five criteria:

### A. Provenance Completeness
Verifies the presence of all statutory metadata fields required for financial citations:
- `chunk_id`, `ticker`, `cik`, `filing_type`, `filing_date`, `accession_number`, `section_identifier`, `source_url`.
- Missing fields flag `incomplete_provenance`.

### B. SEC EDGAR Domain Whitelist
Verifies that all `source_url` attributes belong to approved official SEC EDGAR archive hosts:
- Whitelist: `www.sec.gov`, `sec.gov`, `data.sec.gov`, `archives.sec.gov`.
- Non-whitelisted domains raise security alerts and flag `requires_review`.

### C. Stored Document Consistency
If `DocumentStorage` is active, chunks are verified against persistent SQLite records:
- Accession number existence.
- Verification that chunk ticker matches registered document ticker and filing type.
- Mismatches trigger `source_mismatch`.

### D. Duplicate and Near-Duplicate Detection
- **Exact Duplicate IDs**: Flagged as `possible_duplicate`.
- **Verbatim Text Duplicates**: Flagged as `possible_duplicate`.
- **Textual Overlap**: Computes token-level Jaccard similarity across chunks from the same accession and section. Chunks with $\ge 70\%$ word overlap are clustered as near-duplicates.

### E. Temporal Context & Period Divergence
- Detects whether candidate passages refer to differing financial periods (e.g. FY2022 vs FY2023 or Q1 vs Q3).
- If multiple distinct reporting dates are retrieved for a single query, the validator flags `temporal_mismatch` and issues structured warning alerts advising downstream LLM systems **not to treat disclosures from different reporting periods as interchangeable evidence**.

---

## 7. REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/evaluation/retrieval/run` | Executes IR evaluation on a benchmark dataset for a specific retrieval modality. |
| `POST` | `/api/v1/evaluation/retrieval/compare` | Runs comparative multi-retriever benchmark across Dense, Sparse, Hybrid, and Reranked search. |
| `POST` | `/api/v1/evaluation/evidence/validate` | Audits evidence passages by natural language query or by chunk IDs list. |
| `GET` | `/api/v1/evaluation/retrieval/reports/{report_id}` | Retrieves a previously generated evaluation report by ID. |
| `GET` | `/api/v1/retrieval/reranker/status` | Returns operational status, initialization state, model, device, and benchmark latency. |

---

## 8. Streamlit Frontend Workspace

The **Retrieval Evaluation & Evidence Quality** workspace in `frontend/app.py` provides:
1. **Retrieval Comparison Tab**: Interactive parameter controls (top-k cutoff slider, reranker toggle, ticker filter), metrics summary table, comparative delta callouts, and latency comparisons.
2. **Per-Query Inspector Tab**: Dropdown selection across evaluated queries displaying ground-truth relevant IDs, retrieved chunks, rank positions, and per-query precision, recall, and NDCG scores.
3. **Reranker Benchmark Tab**: Displays cross-encoder model name, initialization status, compute device, candidate over-fetch mechanics, and live CPU latency benchmark tools.
4. **Evidence Quality Validator Tab**: Interactive natural language query and chunk ID input modes, overall audit status indicators (Valid, Requires Review, Invalid), multi-period temporal warnings, and per-chunk provenance audit tables with direct SEC EDGAR citation links.

---

## 9. Verification & Test Suite

The test suite covers:
- **Retrieval Metrics**: Precision, Recall, MRR, MAP, NDCG, Coverage, deduplication, edge cases (`tests/test_retrieval_evaluator.py`).
- **Cross-Encoder Reranker**: Lazy loading, mock prediction, rank reordering, provenance preservation, batching, disabled mode, latency benchmarking (`tests/test_cross_encoder_reranker.py`).
- **Retrieval Comparison**: Multi-method evaluation, relative delta calculations, per-query comparison tables (`tests/test_retrieval_comparison.py`).
- **Evidence Validator**: Provenance checks, SEC URL whitelists, database consistency, duplicate detection, temporal mismatch alerts (`tests/test_evidence_validator.py`).
- **Evidence Report**: Query-level report assembly, validation linking, SEC source link aggregation (`tests/test_evidence_report.py`).
- **FastAPI Endpoints**: Request/response contracts, 404 handling, parameter filtering, report retrieval (`tests/test_api_evaluation.py`).

All standard unit and integration tests run **100% offline** with zero network calls and zero model downloads.
