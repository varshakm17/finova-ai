"""Hybrid Search Engine combining Dense Semantic Retrieval and BM25 Sparse Search.

Applies Reciprocal Rank Fusion (RRF) to blend vector similarity and lexical
exact matches into a unified, deterministic ranking with full statutory provenance.
"""

from __future__ import annotations

import time
from typing import Any

from backend.data.document_storage import DocumentStorage
from backend.retrieval.bm25_search import BM25SearchService
from backend.retrieval.retrieval_models import (
    HybridSearchResponse,
    HybridSearchResult,
    SemanticSearchResult,
)
from backend.retrieval.semantic_search import SemanticSearchService
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("hybrid_search")


class HybridSearchService:
    """Orchestrates multi-modal retrieval blending dense embeddings and sparse BM25."""

    def __init__(
        self,
        semantic_search_service: SemanticSearchService | None = None,
        bm25_search_service: BM25SearchService | None = None,
        document_storage: DocumentStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.semantic_search = semantic_search_service or SemanticSearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.bm25_search = bm25_search_service or BM25SearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )

    @staticmethod
    def calculate_rrf_score(
        rank: int,
        rrf_constant: int = 60,
    ) -> float:
        """Compute single-list Reciprocal Rank contribution: 1 / (k + rank)."""
        return 1.0 / (rrf_constant + rank)

    def search(
        self,
        query: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        top_k: int = 5,
        rrf_constant: int = 60,
        dense_limit: int = 50,
        sparse_limit: int = 50,
    ) -> HybridSearchResponse:
        """Execute hybrid search combining dense semantic and BM25 sparse retrieval.

        Args:
            query: Natural-language or keyword search query.
            ticker: Optional ticker symbol filter.
            filing_type: Optional filing type filter (e.g. '10-K', '10-Q').
            section_identifier: Optional section filter (e.g. 'ITEM_1A', 'ITEM_7').
            top_k: Number of ranked hybrid results to return.
            rrf_constant: RRF smoothing constant k (standard: 60).
            dense_limit: Candidate pool size retrieved from dense search.
            sparse_limit: Candidate pool size retrieved from sparse search.

        Returns:
            HybridSearchResponse: Fused results and diagnostics.

        Raises:
            ValueError: If query is empty or whitespace-only.
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty or whitespace-only.")

        clean_query = query.strip()
        warnings: list[str] = []
        retrieval_mode = "hybrid"
        status = "success"

        start_time = time.perf_counter()

        # 1. Execute Dense Semantic Search
        dense_results: list[SemanticSearchResult] = []
        dense_failed = False
        dense_duration = 0.0

        try:
            d_start = time.perf_counter()
            dense_results = self.semantic_search.search(
                query=clean_query,
                ticker=ticker,
                filing_type=filing_type,
                section_identifier=section_identifier,
                top_k=dense_limit,
                similarity_threshold=-1.0,  # Do not pre-cutoff candidates before fusion
            )
            dense_duration = time.perf_counter() - d_start
        except Exception as exc:  # noqa: BLE001
            logger.error("Dense search failed: %s", exc)
            dense_failed = True
            warnings.append(f"Dense semantic search failed: {exc}")

        # 2. Execute BM25 Sparse Search
        sparse_results: list[Any] = []
        sparse_failed = False
        sparse_duration = 0.0

        try:
            s_start = time.perf_counter()
            sparse_results = self.bm25_search.search(
                query=clean_query,
                ticker=ticker,
                filing_type=filing_type,
                section_identifier=section_identifier,
                top_k=sparse_limit,
            )
            sparse_duration = time.perf_counter() - s_start
        except Exception as exc:  # noqa: BLE001
            logger.error("BM25 search failed: %s", exc)
            sparse_failed = True
            warnings.append(f"BM25 sparse search failed: {exc}")

        # 3. Handle Degraded-Mode Status
        if dense_failed and sparse_failed:
            status = "error"
            elapsed = time.perf_counter() - start_time
            return HybridSearchResponse(
                query=clean_query,
                retrieval_mode="hybrid_failed",
                status="error",
                total_results=0,
                results=[],
                diagnostics={
                    "total_duration_seconds": round(elapsed, 4),
                    "dense_candidates": 0,
                    "sparse_candidates": 0,
                },
                warnings=warnings,
            )
        elif dense_failed:
            retrieval_mode = "hybrid_degraded_sparse_only"
            status = "degraded"
        elif sparse_failed:
            retrieval_mode = "hybrid_degraded_dense_only"
            status = "degraded"

        # 4. Map and Index Candidates
        # Map: chunk_id -> dict with details
        candidates: dict[str, dict[str, Any]] = {}

        # Process Dense Results (1-based ranking)
        for rank_idx, d_res in enumerate(dense_results, start=1):
            cid = d_res.chunk_id
            candidates[cid] = {
                "chunk_id": cid,
                "ticker": d_res.ticker,
                "company_name": d_res.company_name,
                "cik": d_res.cik,
                "filing_type": d_res.filing_type,
                "filing_date": d_res.filing_date,
                "report_date": d_res.report_date,
                "accession_number": d_res.accession_number,
                "section_identifier": d_res.section_identifier,
                "section_title": d_res.section_title,
                "chunk_text": d_res.chunk_text,
                "source_url": d_res.source_url,
                "dense_rank": rank_idx,
                "dense_score": d_res.similarity_score,
                "sparse_rank": None,
                "bm25_score": None,
                "retrieval_sources": ["dense"],
                "rrf_score": self.calculate_rrf_score(rank_idx, rrf_constant),
            }

        # Process Sparse BM25 Results (1-based ranking)
        for rank_idx, s_res in enumerate(sparse_results, start=1):
            cid = s_res.chunk_id
            sparse_rrf = self.calculate_rrf_score(rank_idx, rrf_constant)

            if cid in candidates:
                # Chunk found in both dense and sparse lists
                candidates[cid]["sparse_rank"] = rank_idx
                candidates[cid]["bm25_score"] = s_res.bm25_score
                candidates[cid]["rrf_score"] += sparse_rrf
                candidates[cid]["retrieval_sources"].append("sparse")
            else:
                # Chunk found only in sparse list
                candidates[cid] = {
                    "chunk_id": cid,
                    "ticker": s_res.ticker,
                    "company_name": s_res.company_name,
                    "cik": s_res.cik,
                    "filing_type": s_res.filing_type,
                    "filing_date": s_res.filing_date,
                    "report_date": s_res.report_date,
                    "accession_number": s_res.accession_number,
                    "section_identifier": s_res.section_identifier,
                    "section_title": s_res.section_title,
                    "chunk_text": s_res.chunk_text,
                    "source_url": s_res.source_url,
                    "dense_rank": None,
                    "dense_score": None,
                    "sparse_rank": rank_idx,
                    "bm25_score": s_res.bm25_score,
                    "retrieval_sources": ["sparse"],
                    "rrf_score": sparse_rrf,
                }

        # 5. Deterministic Tie-Breaking & Sorting
        # Key: (-rrf_score, -len(sources), min_rank, chunk_id)
        def sort_key(item: dict[str, Any]) -> tuple:
            # Multi-source preferred over single source
            src_count = len(item["retrieval_sources"])
            # Best individual rank
            d_rank = item["dense_rank"] if item["dense_rank"] is not None else 999999
            s_rank = item["sparse_rank"] if item["sparse_rank"] is not None else 999999
            best_rank = min(d_rank, s_rank)
            return (
                -item["rrf_score"],
                -src_count,
                best_rank,
                item["chunk_id"],
            )

        sorted_candidates = sorted(candidates.values(), key=sort_key)
        top_candidates = sorted_candidates[:top_k]

        final_results = [
            HybridSearchResult(
                chunk_id=c["chunk_id"],
                ticker=c["ticker"],
                company_name=c["company_name"],
                cik=c["cik"],
                filing_type=c["filing_type"],
                filing_date=c["filing_date"],
                report_date=c["report_date"],
                accession_number=c["accession_number"],
                section_identifier=c["section_identifier"],
                section_title=c["section_title"],
                chunk_text=c["chunk_text"],
                source_url=c["source_url"],
                dense_rank=c["dense_rank"],
                dense_score=c["dense_score"],
                sparse_rank=c["sparse_rank"],
                bm25_score=c["bm25_score"],
                rrf_score=round(c["rrf_score"], 6),
                retrieval_sources=c["retrieval_sources"],
            )
            for c in top_candidates
        ]

        total_elapsed = time.perf_counter() - start_time

        # Calculate diagnostics
        overlap_count = sum(
            1 for c in candidates.values() if len(c["retrieval_sources"]) == 2
        )
        diagnostics = {
            "total_duration_seconds": round(total_elapsed, 4),
            "dense_duration_seconds": round(dense_duration, 4),
            "sparse_duration_seconds": round(sparse_duration, 4),
            "dense_candidates_count": len(dense_results),
            "sparse_candidates_count": len(sparse_results),
            "total_unique_candidates": len(candidates),
            "overlap_candidates_count": overlap_count,
            "rrf_constant": rrf_constant,
            "top_k": top_k,
        }

        return HybridSearchResponse(
            query=clean_query,
            retrieval_mode=retrieval_mode,
            status=status,
            total_results=len(final_results),
            results=final_results,
            diagnostics=diagnostics,
            warnings=warnings,
        )
