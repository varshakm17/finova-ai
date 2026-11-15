# BM25 Sparse Retrieval & Hybrid Search with Reciprocal Rank Fusion

Finova AI — Session 06 Multi-Modal Retrieval Architecture & Operational Guide

---

## 1. Executive Summary

Session 06 extends Finova AI's retrieval capabilities by integrating sparse lexical search (BM25) with the existing dense semantic vector index (Session 05) using **Reciprocal Rank Fusion (RRF)**. Corporate statutory disclosures contain exact numerical codes, XBRL tags, acronyms, and statutory legal phrases where dense embeddings alone can struggle to resolve exact keyword matches. Conversely, sparse keyword search struggles with conceptual paraphrases and synonymy.

The hybrid engine unifies both paradigms:
1. **Dense Semantic Retrieval**: High-recall conceptual similarity using local CPU-optimized SentenceTransformers (`all-MiniLM-L6-v2`) over 384-dimensional normalized vectors.
2. **Sparse Lexical Retrieval (BM25)**: High-precision exact term matching using `FinancialBM25` (Robertson/Lucene smoothed IDF) and a specialized domain tokenizer preserving currencies, percentages, dates, statutory forms, and hyphenated terms.
3. **Reciprocal Rank Fusion (RRF)**: A rank-based combination algorithm ($k=60$) blending disparate score spaces into a single, calibrated, and deterministic ranking with complete SEC EDGAR source provenance.

---

## 2. Multi-Modal Retrieval Architecture

```mermaid
flowchart TD
    UserQuery["User Natural-Language Query"] --> Tokenizer["FinancialTokenizer<br/>(backend/retrieval/bm25_search.py)"]
    UserQuery --> Embeddings["EmbeddingService<br/>(backend/retrieval/embedding_service.py)"]

    subgraph Sparse BM25 Retrieval
        Tokenizer -->|"Normalized Tokens"| BM25["BM25SearchService<br/>(FinancialBM25 / BM25Okapi)"]
        BM25Idx[("BM25 Corpus & Hashes<br/>datasets/indexes/bm25/")] --> BM25
        BM25 -->|"Top M Lexical Candidates (Rank & BM25 Score)"| Fusion
    end

    subgraph Dense Semantic Retrieval
        Embeddings -->|"384D Query Vector"| Dense["SemanticSearchService<br/>(FaissVectorStore / NumpyVectorStore)"]
        DenseIdx[("Dense Vector Index<br/>datasets/indexes/")] --> Dense
        Dense -->|"Top N Dense Candidates (Rank & Cosine Score)"| Fusion
    end

    subgraph Reciprocal Rank Fusion (RRF)
        Fusion["HybridSearchService<br/>(backend/retrieval/hybrid_search.py)"]
        Fusion -->|"Calculate RRF: sum(1 / (k + rank))"| Dedupe["Deduplication & Provenance Resolution"]
        Dedupe -->|"Joined Document Metadata"| SQLite[("SQLite Database<br/>(finova.db)")]
        Dedupe -->|"Metadata Filters (Ticker, Form, Section)"| Filter["Filter & Deterministic Tie-Breaking"]
    end

    Filter --> Results["Final Ranked Hybrid Results<br/>(Combined RRF Scores, Sources, & SEC Citations)"]
```

---

## 3. Financial Tokenizer & Vocabulary Preservation

Statutory financial disclosures require tokenization rules that preserve quantitative and domain-specific terminology:

### 3.1. Preserved Financial Patterns
- **Monetary Expressions**: `r"\$\d+(?:,\d{3})*(?:\.\d+)?"` (e.g. `$5.2`, `$1,250.75`, `$50`).
- **Percentages**: `r"\d+(?:\.\d+)?%"` (e.g. `15.4%`, `44.1%`, `10%`).
- **Hyphenated Terms & Statutory Codes**: `r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+"` (e.g. `year-over-year`, `10-K`, `10-Q`, `non-GAAP`, `cash-flow`, `debt-to-equity`, `cost-of-goods-sold`).
- **Numbers, Years, and Decimals**: `r"\d+(?:,\d{3})*(?:\.\d+)?"` (e.g. `2023`, `100`, `3.14`).
- **Acronyms & Financial Concepts**: `r"[a-zA-Z0-9_]+"` (e.g. `EBITDA`, `GAAP`, `CAGR`, `revenue`, `Item_1A`).

### 3.2. Safe Stopword Handling
Only high-frequency English function words (`the`, `a`, `an`, `and`, `or`, `in`, `of`, `to`, `for`, `is`, `are`, `was`, `were`, `with`, `by`, `from`, `that`, `this`, `it`) are filtered.
Financial numbers, percentages, dates, and quantitative nouns are strictly excluded from stopword lists.

---

## 4. Sparse Index Persistence & Incremental Updates

BM25 does not require GPU compute, but tokenizing tens of thousands of chunks on every search request would introduce unacceptable latency. Finova AI implements safe, incremental, and persistent BM25 indexing:

### 4.1. Safe JSON Persistence
All runtime components serialize to standard human-readable JSON files under `datasets/indexes/bm25/`:
- `bm25_index_ids.json`: Ordered array of chunk IDs (`chunk_id`).
- `bm25_tokenized_corpus.json`: Array of token arrays matching index positions.
- `bm25_hashes.json`: Dictionary mapping `chunk_id -> SHA256(chunk_text)`.
- `bm25_meta.json`: Diagnostic metadata (`tokenizer_version`, `k1`, `b`, `total_chunks`, `total_tokens`, `avg_doc_len`).

> [!NOTE]
> Finova AI completely avoids unsafe Python `pickle` serialization. The BM25 model is dynamically reconstructed in sub-milliseconds from persisted token lists during index initialization.

### 4.2. SQLite Index Metadata Tracking
Metadata state is tracked inside SQLite table `bm25_index_metadata`:
```sql
CREATE TABLE IF NOT EXISTS bm25_index_metadata (
    index_id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    section_identifier TEXT NOT NULL,
    tokenizer_version TEXT NOT NULL DEFAULT '1.0.0',
    content_hash TEXT NOT NULL,
    doc_len INTEGER NOT NULL,
    index_status TEXT NOT NULL DEFAULT 'indexed',
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (chunk_id) REFERENCES document_chunks (chunk_id) ON DELETE CASCADE,
    UNIQUE(chunk_id, tokenizer_version)
);
```

### 4.3. Incremental Indexing Lifecycle (`BM25IndexingService`)
1. **Discovery**: Identifies all chunks matching the company/filing scope.
2. **Hash Comparison**: Compares the SHA-256 digest of chunk text against `bm25_index_metadata`.
3. **Differential Updates**:
   - `already_indexed`: Chunks with matching hashes and present in the in-memory index are skipped with zero cost.
   - `newly_indexed`: Previously unseen chunks are tokenized and appended.
   - `updated_indexed`: Modified chunks or force-reindexed chunks are re-tokenized and updated in-place.
4. **Model Refresh**: Rebuilds the runtime `FinancialBM25` model once per batch and persists updated state to disk and database.

---

## 5. Reciprocal Rank Fusion (RRF)

### 5.1. Mathematical Formulation
Directly adding dense cosine similarity scores (typically bounded between `[-1.0, 1.0]`) and raw BM25 scores (unbounded positive floats, e.g. `[0.0, 35.0+]`) produces distorted rankings due to incompatible distributions and scale disparities.

Instead, Reciprocal Rank Fusion (Cormack et al., 2009) operates entirely on **ordinal rank positions**:

$$RRF(d) = \sum_{r \in R} \frac{1}{k + rank_r(d)}$$

Where:
- $d$ is a candidate document chunk.
- $R$ is the set of retrieval systems ($R = \{\text{dense}, \text{sparse}\}$).
- $rank_r(d)$ is the 1-based rank of chunk $d$ in the result list of retriever $r$ ($1, 2, 3, \dots$).
- $k$ is the smoothing constant (standard default: $60$).

### 5.2. Fusion Cases
1. **Mutual Candidates (Present in both lists)**:
   $$RRF(d) = \frac{1}{k + rank_{\text{dense}}(d)} + \frac{1}{k + rank_{\text{sparse}}(d)}$$
   *Example ($k=60$):* A chunk ranked #1 in dense and #2 in sparse receives:
   $$\frac{1}{61} + \frac{1}{62} \approx 0.016393 + 0.016129 = 0.032522$$
2. **Dense-Only Candidates**:
   $$RRF(d) = \frac{1}{k + rank_{\text{dense}}(d)}$$
   *Example:* Rank #1 dense receives $\frac{1}{61} \approx 0.016393$.
3. **Sparse-Only Candidates**:
   $$RRF(d) = \frac{1}{k + rank_{\text{sparse}}(d)}$$
   *Example:* Rank #1 sparse receives $\frac{1}{61} \approx 0.016393$.

### 5.3. Deterministic Tie-Breaking
When two candidates share identical RRF scores, ties are resolved deterministically using:
1. Higher RRF score (descending).
2. Number of retrieval sources (candidates appearing in both sources are preferred over single-source candidates).
3. Best individual rank ($\min(rank_{\text{dense}}, rank_{\text{sparse}})$).
4. Chunk ID string collation.

---

## 6. Degraded-Mode Architecture & Fault Tolerance

If an individual retrieval backend encounters an error (e.g. missing FAISS index, corrupted JSON, or model loading exception), the hybrid service gracefully degrades:
- **Dense Failure**: Executes BM25 sparse search only. Returns results with `retrieval_mode="hybrid_degraded_sparse_only"`, `status="degraded"`, and logs an informative warning.
- **Sparse Failure**: Executes dense semantic search only. Returns results with `retrieval_mode="hybrid_degraded_dense_only"`, `status="degraded"`, and logs an informative warning.
- **Mutual Failure**: Returns `retrieval_mode="hybrid_failed"`, `status="error"`, and details the failure reasons.

---

## 7. REST API Reference

### 7.1. Build or Refresh BM25 Index
`POST /api/v1/companies/{ticker}/bm25/index`

**Query / Body Parameters:**
- `filing_type` (optional): Filter by statutory form (e.g. `10-K`).
- `accession_number` (optional): Filter by specific SEC filing accession.
- `force_reindex` (boolean): Default `false`.

**Response (`200 OK`):**
```json
{
  "ticker": "AAPL",
  "total_discovered": 48,
  "already_indexed": 48,
  "newly_indexed": 0,
  "updated_indexed": 0,
  "removed": 0,
  "failed": 0,
  "tokenizer_version": "1.0.0",
  "duration_seconds": 0.024,
  "message": "BM25 indexing complete for AAPL: 0 new, 0 updated, 48 skipped, 0 failed."
}
```

---

### 7.2. Get BM25 Status
`GET /api/v1/companies/{ticker}/bm25/status`

**Response (`200 OK`):**
```json
{
  "ticker": "AAPL",
  "total_available_chunks": 48,
  "indexed_chunks": 48,
  "pending_chunks": 0,
  "failed_chunks": 0,
  "tokenizer_version": "1.0.0",
  "total_tokens": 28410,
  "avg_doc_len": 591.88,
  "last_indexed_at": "2026-11-15T20:30:00Z"
}
```

---

### 7.3. Sparse Lexical Search
`POST /api/v1/search/sparse`

**Request Body:**
```json
{
  "query": "operating cash-flow and debt-to-equity ratio",
  "ticker": "AAPL",
  "filing_type": "10-K",
  "section_identifier": "ITEM_7",
  "top_k": 5
}
```

**Response (`200 OK`):**
```json
[
  {
    "chunk_id": "doc_0000320193_10K_ITEM_7_0",
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "cik": "0000320193",
    "filing_type": "10-K",
    "filing_date": "2023-11-03",
    "report_date": "2023-09-30",
    "accession_number": "0000320193-23-000106",
    "section_identifier": "ITEM_7",
    "section_title": "Item 7. MD&A",
    "chunk_text": "Operating cash-flow increased year-over-year to $110 billion...",
    "bm25_score": 14.82,
    "source_url": "https://www.sec.gov/Archives/...",
    "matched_terms": ["cash-flow", "debt-to-equity", "operating"]
  }
]
```

---

### 7.4. Hybrid Search with Reciprocal Rank Fusion
`POST /api/v1/search/hybrid`

**Request Body:**
```json
{
  "query": "What supply chain disruptions affect international manufacturing?",
  "ticker": "AAPL",
  "filing_type": "10-K",
  "section_identifier": "ITEM_1A",
  "top_k": 5,
  "rrf_constant": 60,
  "dense_limit": 50,
  "sparse_limit": 50
}
```

**Response (`200 OK`):**
```json
{
  "query": "What supply chain disruptions affect international manufacturing?",
  "retrieval_mode": "hybrid",
  "status": "success",
  "total_results": 1,
  "results": [
    {
      "chunk_id": "doc_0000320193_10K_ITEM_1A_0",
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "cik": "0000320193",
      "filing_type": "10-K",
      "filing_date": "2023-11-03",
      "report_date": "2023-09-30",
      "accession_number": "0000320193-23-000106",
      "section_identifier": "ITEM_1A",
      "section_title": "Item 1A. Risk Factors",
      "chunk_text": "Global supply chain disruptions and semiconductor shortages in Asia...",
      "source_url": "https://www.sec.gov/Archives/...",
      "dense_rank": 1,
      "dense_score": 0.8142,
      "sparse_rank": 1,
      "bm25_score": 12.45,
      "rrf_score": 0.032787,
      "retrieval_sources": ["dense", "sparse"]
    }
  ],
  "diagnostics": {
    "total_duration_seconds": 0.035,
    "dense_duration_seconds": 0.025,
    "sparse_duration_seconds": 0.008,
    "dense_candidates_count": 50,
    "sparse_candidates_count": 22,
    "total_unique_candidates": 58,
    "overlap_candidates_count": 14,
    "rrf_constant": 60,
    "top_k": 5
  },
  "warnings": []
}
```

---

## 8. Evaluation & Diagnostics (`RetrievalDiagnostics`)

Located in `backend/evaluation/retrieval_diagnostics.py`, this suite evaluates multi-modal retrieval behavior:
- **Candidate Overlap & Jaccard Ratio**:
  $$J(\text{Dense}, \text{Sparse}) = \frac{|\text{Dense} \cap \text{Sparse}|}{|\text{Dense} \cup \text{Sparse}|}$$
- **Exclusive Contribution Metrics**: Quantifies chunks discovered exclusively by dense search vs. exclusively by sparse search.
- **Rank Shift Analysis**: Tracks how candidate rankings change when moving from individual retriever lists to fused hybrid rank.
- **Synthetic Query Suite**: 4 standardized SEC disclosure evaluation queries covering risk disclosures, revenue trends, liquidity, and market risks for automated offline regression verification.

