"""Query-Level Evidence Report Generator for Finova AI.

Consolidates retrieved candidates, ranking metadata, cross-encoder scores,
statutory provenance validation, and SEC source citations into an audit-ready,
LLM-independent evidence report.
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.data.document_storage import DocumentStorage
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import (
    EvidenceReport,
    HybridSearchResult,
    RerankedSearchResult,
)
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("evidence_report")


class EvidenceReportGenerator:
    """Orchestrates retrieval, reranking, evidence validation, and report generation."""

    def __init__(
        self,
        hybrid_search_service: HybridSearchService | None = None,
        reranker: CrossEncoderReranker | None = None,
        validator: EvidenceQualityValidator | None = None,
        document_storage: DocumentStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.doc_storage = document_storage or DocumentStorage()
        self.hybrid_search = hybrid_search_service or HybridSearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.reranker = reranker or CrossEncoderReranker(settings=self.settings)
        self.validator = validator or EvidenceQualityValidator(
            document_storage=self.doc_storage,
            settings=self.settings,
        )

    def generate_report(
        self,
        query: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        top_k: int = 5,
        apply_reranking: bool = True,
    ) -> EvidenceReport:
        """Execute end-to-end retrieval, validation, and assemble an EvidenceReport.

        Args:
            query: Financial inquiry or research question.
            ticker: Optional company ticker filter.
            filing_type: Optional statutory form type.
            section_identifier: Optional canonical section filter.
            top_k: Number of ranked evidence passages to include.
            apply_reranking: Whether to apply cross-encoder reranking stage.

        Returns:
            EvidenceReport with validated candidates, audit statuses, and SEC links.
        """
        # 1. Fetch initial candidates from Hybrid Search
        cand_count = max(top_k * 4, self.settings.RERANKER_CANDIDATE_COUNT)
        hybrid_resp = self.hybrid_search.search(
            query=query,
            ticker=ticker,
            filing_type=filing_type,
            section_identifier=section_identifier,
            top_k=cand_count,
        )

        candidates = hybrid_resp.results
        reranker_applied = False
        reranker_model: str | None = None

        # 2. Apply cross-encoder reranking if requested and available
        final_candidates: list[HybridSearchResult | RerankedSearchResult]
        if apply_reranking and self.reranker.is_available:
            reranked_results, meta = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k,
            )
            final_candidates = reranked_results
            reranker_applied = meta.get("reranker_applied", False)
            reranker_model = meta.get("model_name", self.settings.RERANKER_MODEL_NAME)
        else:
            final_candidates = candidates[:top_k]

        # 3. Deterministic Evidence Quality Validation
        validation_result = self.validator.validate_chunks(final_candidates)

        # 4. Map candidate records with validation statuses
        ranked_records: list[dict[str, Any]] = []
        sec_links: set[str] = set()

        for idx, cand in enumerate(final_candidates):
            c_val = (
                validation_result.chunk_validations[idx]
                if idx < len(validation_result.chunk_validations)
                else None
            )

            is_reranked = isinstance(cand, RerankedSearchResult)
            url = cand.source_url
            if url:
                sec_links.add(url)

            rec: dict[str, Any] = {
                "chunk_id": cand.chunk_id,
                "ticker": cand.ticker,
                "company_name": cand.company_name,
                "cik": cand.cik,
                "filing_type": cand.filing_type,
                "filing_date": cand.filing_date,
                "report_date": cand.report_date,
                "accession_number": cand.accession_number,
                "section_identifier": cand.section_identifier,
                "section_title": cand.section_title,
                "chunk_text": cand.chunk_text,
                "source_url": cand.source_url,
                "rank": idx + 1,
                "dense_rank": cand.original_dense_rank
                if is_reranked
                else cand.dense_rank,
                "dense_score": cand.original_dense_score
                if is_reranked
                else cand.dense_score,
                "sparse_rank": cand.original_sparse_rank
                if is_reranked
                else cand.sparse_rank,
                "bm25_score": cand.original_bm25_score
                if is_reranked
                else cand.bm25_score,
                "rrf_score": cand.original_rrf_score if is_reranked else cand.rrf_score,
                "retrieval_sources": cand.retrieval_sources,
                "validation_status": c_val.status if c_val else "valid",
                "validation_warnings": c_val.warnings if c_val else [],
                "is_duplicate": c_val.is_duplicate if c_val else False,
            }

            if is_reranked:
                rec["rerank_score"] = cand.rerank_score
                rec["original_rank"] = cand.original_rank

            ranked_records.append(rec)

        report_method = (
            "hybrid_reranked"
            if reranker_applied
            else (
                "hybrid"
                if hybrid_resp.retrieval_mode == "hybrid"
                else hybrid_resp.retrieval_mode
            )
        )

        return EvidenceReport(
            report_id=f"ev_rep_{uuid.uuid4().hex[:12]}",
            query=query,
            retrieval_method=report_method,
            reranker_applied=reranker_applied,
            reranker_model=reranker_model,
            ranked_candidates=ranked_records,
            validation_summary=validation_result,
            distinct_periods=validation_result.distinct_reporting_periods,
            sec_source_links=sorted(sec_links),
        )
