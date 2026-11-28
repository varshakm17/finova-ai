"""Context Builder for Evidence-Grounded Financial RAG.

Orchestrates multi-modal retrieval, cross-encoder reranking, evidence quality
filtering, and deterministic financial calculation integration into a structured,
citation-ready context string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.rag.rag_models import (
    CalculationEvidence,
    RetrievedEvidence,
)
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.retrieval.retrieval_models import (
    HybridSearchResult,
    RerankedSearchResult,
)
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("context_builder")

# Financial calculation metric keyword triggers
METRIC_KEYWORD_MAP: dict[str, list[str]] = {
    "revenue_growth": [
        "revenue growth",
        "sales growth",
        "growth rate",
        "topline growth",
    ],
    "gross_margin": ["gross margin", "gross profit margin"],
    "operating_margin": ["operating margin", "operating profit margin", "ebit margin"],
    "net_margin": ["net margin", "net profit margin", "bottom line margin"],
    "current_ratio": ["current ratio", "liquidity ratio", "short term liquidity"],
    "quick_ratio": ["quick ratio", "acid test"],
    "debt_to_equity": [
        "debt to equity",
        "debt-to-equity",
        "leverage ratio",
        "d/e ratio",
    ],
    "return_on_assets": ["return on assets", "roa"],
    "return_on_equity": ["return on equity", "roe"],
    "free_cash_flow": ["free cash flow", "fcf", "cash flow generated"],
}


@dataclass
class BuiltContext:
    """Container holding assembled context text, structured evidence items, and metadata."""

    prompt_context_text: str
    retrieved_evidence: list[RetrievedEvidence] = field(default_factory=list)
    calculation_evidence: list[CalculationEvidence] = field(default_factory=list)
    retrieval_method: str = "hybrid"
    warnings: list[str] = field(default_factory=list)
    has_sufficient_evidence: bool = True


class RAGContextBuilder:
    """Assembles validated filing passages and deterministic calculation receipts."""

    def __init__(
        self,
        hybrid_search_service: HybridSearchService | None = None,
        reranker: CrossEncoderReranker | None = None,
        validator: EvidenceQualityValidator | None = None,
        database: Database | None = None,
        document_storage: DocumentStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = database or Database()
        self.doc_storage = document_storage or DocumentStorage(db=self.db)
        self.hybrid_search = hybrid_search_service or HybridSearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.reranker = reranker or CrossEncoderReranker(settings=self.settings)
        self.validator = validator or EvidenceQualityValidator(
            document_storage=self.doc_storage,
            settings=self.settings,
        )

    def identify_relevant_metrics(self, question: str) -> list[str]:
        """Detect canonical financial calculation metrics referenced in user question."""
        q_lower = question.lower()
        matched_metrics: list[str] = []
        for metric_name, keywords in METRIC_KEYWORD_MAP.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", q_lower):
                    matched_metrics.append(metric_name)
                    break
        return matched_metrics

    def fetch_calculation_evidence(
        self,
        ticker: str | None,
        question: str,
        limit_per_metric: int = 3,
    ) -> list[CalculationEvidence]:
        """Query stored calculation receipts matching metrics referenced in question."""
        if not ticker:
            return []

        matched_metrics = self.identify_relevant_metrics(question)
        if not matched_metrics:
            return []

        calc_evidence_list: list[CalculationEvidence] = []
        c_idx = 1

        for metric in matched_metrics:
            try:
                receipts = self.db.get_financial_calculations(
                    ticker_or_cik=ticker,
                    metric_name=metric,
                    limit=limit_per_metric,
                )
                for rec in receipts:
                    calc_id = str(rec.get("calculation_id", f"calc_{c_idx}"))
                    val = float(rec.get("calculated_value", 0.0))
                    evidence_id = f"C{c_idx}"
                    c_idx += 1

                    fy = rec.get("fiscal_year")
                    pe_str = str(rec.get("period_end") or "")
                    if fy is None and pe_str and len(pe_str) >= 4 and pe_str[:4].isdigit():
                        fy = int(pe_str[:4])

                    calc_evidence_list.append(
                        CalculationEvidence(
                            evidence_id=evidence_id,
                            calculation_id=calc_id,
                            metric_name=str(rec.get("metric_name", metric)),
                            calculated_value=val,
                            unit=str(rec.get("unit", "")),
                            formula=str(rec.get("formula_expression", "")),
                            period_start=rec.get("period_start"),
                            period_end=pe_str,
                            fiscal_year=fy,
                            fiscal_period=rec.get("fiscal_period"),
                            input_observations=rec.get("inputs")
                            or rec.get("input_observations")
                            or [],
                            inputs=rec.get("inputs", []),
                            calculation_status=str(rec.get("status", "calculated")),
                        )
                    )
            except Exception as exc:
                logger.warning(
                    "Error fetching calculation receipts for metric '%s': %s",
                    metric,
                    exc,
                )

        return calc_evidence_list

    def build_context(
        self,
        question: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        accession_number: str | None = None,
        top_k: int = 5,
        use_reranker: bool = True,
        include_calculations: bool = True,
    ) -> BuiltContext:
        """Retrieve, validate, and assemble financial context for LLM prompt generation."""
        warnings: list[str] = []

        # 1. Candidate Retrieval via Hybrid Search
        cand_overfetch = max(top_k * 4, self.settings.RERANKER_CANDIDATE_COUNT)
        try:
            hybrid_resp = self.hybrid_search.search(
                query=question,
                ticker=ticker,
                filing_type=filing_type,
                section_identifier=section_identifier,
                top_k=cand_overfetch,
            )
            if hasattr(hybrid_resp, "results"):
                raw_candidates = hybrid_resp.results
                retrieval_mode = getattr(hybrid_resp, "retrieval_mode", "hybrid")
            elif isinstance(hybrid_resp, list):
                raw_candidates = hybrid_resp
                retrieval_mode = "hybrid"
            else:
                raw_candidates = []
                retrieval_mode = "hybrid"
        except Exception as exc:
            logger.error("Hybrid retrieval failed for question '%s': %s", question, exc)
            return BuiltContext(
                prompt_context_text="",
                retrieved_evidence=[],
                calculation_evidence=[],
                retrieval_method="hybrid_failed",
                warnings=[f"Retrieval error: {exc}"],
                has_sufficient_evidence=False,
            )

        if not raw_candidates:
            return BuiltContext(
                prompt_context_text="No relevant SEC filing disclosures were found for this query.",
                retrieved_evidence=[],
                calculation_evidence=[],
                retrieval_method=retrieval_mode,
                warnings=[
                    "Zero candidate passages retrieved matching query and filters.",
                    "No filing passages retrieved for this query.",
                ],
                has_sufficient_evidence=False,
            )

        # Filter by accession number if specified
        if accession_number:
            raw_candidates = [
                c for c in raw_candidates if c.accession_number == accession_number
            ]

        # 2. Optional Cross-Encoder Reranking
        retrieval_method = "hybrid"
        final_candidates: list[HybridSearchResult | RerankedSearchResult]

        if use_reranker and self.reranker.is_available:
            reranked, rerank_meta = self.reranker.rerank(
                query=question,
                candidates=raw_candidates,
                top_k=top_k,
            )
            final_candidates = reranked
            if rerank_meta.get("reranker_applied"):
                retrieval_method = "hybrid_reranked"
        else:
            final_candidates = raw_candidates[:top_k]

        # 3. Deterministic Evidence Quality Validation
        validation_res = self.validator.validate_chunks(final_candidates)

        # 4. Map Candidates into RetrievedEvidence and Filter Invalids
        validated_evidence: list[RetrievedEvidence] = []
        e_idx = 1

        for idx, cand in enumerate(final_candidates):
            c_val = (
                validation_res.chunk_validations[idx]
                if idx < len(validation_res.chunk_validations)
                else None
            )

            # Exclude incomplete provenance or source mismatches
            if c_val and c_val.status in {"incomplete_provenance", "source_mismatch"}:
                warnings.append(
                    f"Excluded candidate chunk '{cand.chunk_id}' due to {c_val.status}."
                )
                continue

            # Record temporal warning
            if c_val and c_val.status == "temporal_mismatch":
                warnings.append(
                    f"Candidate '{cand.chunk_id}' references reporting date '{c_val.reporting_period}' "
                    "amid multi-period evidence. Periods must not be treated as interchangeable."
                )

            is_reranked = isinstance(cand, RerankedSearchResult)
            evidence_id = f"E{e_idx}"
            e_idx += 1

            validated_evidence.append(
                RetrievedEvidence(
                    evidence_id=evidence_id,
                    chunk_id=cand.chunk_id,
                    ticker=cand.ticker,
                    company_name=cand.company_name,
                    filing_type=cand.filing_type,
                    filing_date=cand.filing_date,
                    report_date=cand.report_date,
                    accession_number=cand.accession_number,
                    section_identifier=cand.section_identifier,
                    section_title=cand.section_title,
                    chunk_text=cand.chunk_text,
                    source_url=cand.source_url,
                    dense_score=cand.original_dense_score
                    if is_reranked
                    else cand.dense_score,
                    bm25_score=cand.original_bm25_score
                    if is_reranked
                    else cand.bm25_score,
                    rrf_score=cand.original_rrf_score
                    if is_reranked
                    else cand.rrf_score,
                    reranker_score=cand.rerank_score if is_reranked else None,
                    provenance_status=c_val.status if c_val else "valid",
                )
            )

        # 5. Fetch Calculation Evidence if requested
        calculation_evidence: list[CalculationEvidence] = []
        if include_calculations:
            # Detect ticker from query or first evidence if not explicitly passed
            target_ticker = ticker
            if not target_ticker and validated_evidence:
                target_ticker = validated_evidence[0].ticker

            calculation_evidence = self.fetch_calculation_evidence(
                ticker=target_ticker,
                question=question,
            )

        # Check sufficiency
        has_sufficient = len(validated_evidence) >= self.settings.RAG_MINIMUM_EVIDENCE

        # 6. Format Structured Context Text
        context_blocks: list[str] = []

        if calculation_evidence:
            context_blocks.append(
                "--- VERIFIED FINANCIAL CALCULATIONS (DETERMINISTIC PYTHON RECEIPTS) ---"
            )
            for ce in calculation_evidence:
                val_str = (
                    f"{ce.calculated_value:.2f}%"
                    if ce.unit == "percentage"
                    else f"{ce.calculated_value:.4f} {ce.unit}"
                )
                block = (
                    f"[{ce.evidence_id}] METRIC: {ce.metric_name}\n"
                    f"  Value: {val_str}\n"
                    f"  Formula: {ce.formula}\n"
                    f"  Period: {ce.period_start or 'N/A'} to {ce.period_end}\n"
                    f"  Calculation ID: {ce.calculation_id}"
                )
                context_blocks.append(block)

        context_blocks.append("--- VERIFIED SEC FILING DISCLOSURES ---")
        for ev in validated_evidence:
            block = (
                f"[{ev.evidence_id}] COMPANY: {ev.company_name} ({ev.ticker})\n"
                f"  Filing: {ev.filing_type} (Filed: {ev.filing_date}, Period End: {ev.report_date or 'N/A'})\n"
                f"  Section: {ev.section_title} ({ev.section_identifier})\n"
                f"  Accession: {ev.accession_number}\n"
                f"  Source URL: {ev.source_url}\n"
                f"  Text: {ev.chunk_text}"
            )
            context_blocks.append(block)

        raw_context = "\n\n".join(context_blocks)

        # 7. Context Budget Enforcement
        max_chars = self.settings.RAG_MAX_CONTEXT_CHARACTERS
        if len(raw_context) > max_chars:
            warnings.append(
                f"Context length ({len(raw_context)} chars) exceeded limit ({max_chars} chars). "
                "Truncating lowest-ranked evidence passages while preserving citation metadata."
            )
            # Prune lowest ranked filing evidence while keeping calculations
            while len(raw_context) > max_chars and len(validated_evidence) > 1:
                validated_evidence.pop()
                # Re-render context
                pruned_blocks = []
                if calculation_evidence:
                    pruned_blocks.append(
                        "--- VERIFIED FINANCIAL CALCULATIONS (DETERMINISTIC PYTHON RECEIPTS) ---"
                    )
                    for ce in calculation_evidence:
                        val_str = (
                            f"{ce.calculated_value:.2f}%"
                            if ce.unit == "percentage"
                            else f"{ce.calculated_value:.4f} {ce.unit}"
                        )
                        pruned_blocks.append(
                            f"[{ce.evidence_id}] METRIC: {ce.metric_name}\n"
                            f"  Value: {val_str}\n"
                            f"  Formula: {ce.formula}\n"
                            f"  Period: {ce.period_start or 'N/A'} to {ce.period_end}"
                        )
                pruned_blocks.append("--- VERIFIED SEC FILING DISCLOSURES ---")
                for ev in validated_evidence:
                    pruned_blocks.append(
                        f"[{ev.evidence_id}] COMPANY: {ev.company_name} ({ev.ticker})\n"
                        f"  Filing: {ev.filing_type} (Filed: {ev.filing_date}, Period End: {ev.report_date or 'N/A'})\n"
                        f"  Section: {ev.section_title} ({ev.section_identifier})\n"
                        f"  Accession: {ev.accession_number}\n"
                        f"  Source URL: {ev.source_url}\n"
                        f"  Text: {ev.chunk_text}"
                    )
                raw_context = "\n\n".join(pruned_blocks)

        return BuiltContext(
            prompt_context_text=raw_context,
            retrieved_evidence=validated_evidence,
            calculation_evidence=calculation_evidence,
            retrieval_method=retrieval_method,
            warnings=warnings,
            has_sufficient_evidence=has_sufficient,
        )
