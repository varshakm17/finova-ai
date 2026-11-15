# Finova AI — Retrieval Evaluation Datasets

This directory contains evaluation datasets for measuring information retrieval performance across dense semantic search, BM25 sparse search, Reciprocal Rank Fusion (RRF) hybrid search, and cross-encoder reranking.

---

## 1. Schema Specification

Each evaluation entry in `retrieval_queries.json` follows this structured schema:

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
  "notes": "Synthetic fixture targeting Item 1A Risk Factors."
}
```

### Field Definitions:
- `query_id` (*str*, required): Unique evaluation query identifier (e.g. `EVAL-001`, `REAL-001`).
- `query` (*str*, required): Natural-language research query or financial question.
- `ticker` (*str*, optional): Target company ticker filter (e.g. `AAPL`, `MSFT`).
- `filing_type` (*str*, optional): Statutory SEC form type (e.g. `10-K`, `10-Q`).
- `section_identifier` (*str*, optional): Canonical section filter (e.g. `ITEM_1A`, `ITEM_7`, `ITEM_7A`, `ITEM_1`).
- `relevant_chunk_ids` (*list[str]*, required): Ground-truth relevant document chunk IDs.
- `relevance_grades` (*dict[str, int]*, optional): Graded relevance mapping (`2` = highly relevant, `1` = partially relevant, `0` = non-relevant). Used by NDCG@K.
- `dataset_type` (*str*, required): Must be `"synthetic"` (for algorithmic pipeline tests) or `"curated"` (for human-annotated expert judgments).
- `notes` (*str*, optional): Annotator rationale explaining why the designated chunks answer the query.

---

## 2. Synthetic Fixture vs. Curated Real-World Relevance

> [!IMPORTANT]
> **Synthetic Relevance Fixtures** are used exclusively for automated regression testing and pipeline integrity checks. They verify that the scoring math (Precision, Recall, MRR, MAP, NDCG) and ranking shifts execute correctly. **Synthetic metrics do NOT constitute proof of real-world domain retrieval efficacy.**

> [!NOTE]
> **Curated Real-World Benchmarks** must be annotated by financial analysts inspecting actual SEC 10-K/10-Q text extracted from the database. When curating real-world entries, set `"dataset_type": "curated"`.

