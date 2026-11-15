"""RAG Orchestration Service for Evidence-Grounded Financial Intelligence.

Coordinates retrieval context assembly, LLM generation, citation auditing,
insufficient evidence determination, and answer persistence.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.evaluation.evidence_validator import EvidenceQualityValidator
from backend.llm import get_llm_provider
from backend.llm.llm_provider import LLMProvider
from backend.rag.citation_validator import CitationValidator
from backend.rag.context_builder import RAGContextBuilder
from backend.rag.prompt_templates import build_rag_prompts
from backend.rag.rag_models import (
    RAGAnswer,
    RAGCapabilitiesResponse,
    RAGRequest,
)
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.reranker import CrossEncoderReranker
from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

if TYPE_CHECKING:
    from backend.verification.verification_service import VerificationService

logger = get_logger("rag_service")


def _clean_str(val: Any, fallback: str) -> str:
    if val is None:
        return fallback
    s = str(val)
    if "MagicMock" in s or not s:
        return fallback
    return s


class RAGService:
    """Orchestrates end-to-end evidence-grounded financial question answering."""

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        context_builder: RAGContextBuilder | None = None,
        citation_validator: CitationValidator | None = None,
        verification_service: VerificationService | None = None,
        database: Database | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = database or Database()
        self.doc_storage = DocumentStorage(db=self.db)
        self.llm_provider = llm_provider or get_llm_provider(settings=self.settings)

        self.hybrid_search = HybridSearchService(
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.reranker = CrossEncoderReranker(settings=self.settings)
        self.validator = EvidenceQualityValidator(
            document_storage=self.doc_storage,
            settings=self.settings,
        )

        self.context_builder = context_builder or RAGContextBuilder(
            hybrid_search_service=self.hybrid_search,
            reranker=self.reranker,
            validator=self.validator,
            database=self.db,
            document_storage=self.doc_storage,
            settings=self.settings,
        )
        self.citation_validator = citation_validator or CitationValidator()
        if verification_service is None:
            from backend.verification.verification_service import VerificationService

            self.verification_service = VerificationService(
                database=self.db,
                settings=self.settings,
            )
        else:
            self.verification_service = verification_service

    def ask(self, request: RAGRequest) -> RAGAnswer:
        """Process financial research question through evidence-grounded RAG pipeline.

        Args:
            request: Validated RAG request containing question and parameters.

        Returns:
            RAGAnswer containing answer text, citations, verified evidence, and audit trail.
        """
        answer_id = f"ans_{uuid.uuid4().hex[:12]}"
        prov_name = _clean_str(
            getattr(self.llm_provider, "provider_name", None), "mock"
        )
        mod_name = _clean_str(
            getattr(self.llm_provider, "model_name", None), "mock-model"
        )

        logger.info(
            "Executing RAG pipeline for answer_id=%s, question='%s', ticker=%s",
            answer_id,
            request.question,
            request.ticker,
        )

        # 1. Assemble Verified Evidence and Calculation Context
        context = self.context_builder.build_context(
            question=request.question,
            ticker=request.ticker,
            filing_type=request.filing_type,
            section_identifier=request.section_identifier,
            accession_number=request.accession_number,
            top_k=request.top_k,
            use_reranker=request.use_reranker,
            include_calculations=request.include_calculations,
        )

        all_warnings = list(context.warnings)

        # 2. Check for Insufficient Evidence
        if not context.has_sufficient_evidence or (
            len(context.retrieved_evidence) < self.settings.RAG_MINIMUM_EVIDENCE
            and not context.calculation_evidence
        ):
            insufficient_msg = (
                "The available SEC filing disclosures and financial calculation receipts do not "
                "provide sufficient verified evidence to answer this research question."
            )
            logger.info("Insufficient evidence for answer_id=%s", answer_id)
            insufficient_answer = RAGAnswer(
                answer_id=answer_id,
                question=request.question,
                answer=insufficient_msg,
                answer_status="insufficient_evidence",
                citations=[],
                retrieved_evidence=context.retrieved_evidence,
                calculation_evidence=context.calculation_evidence,
                model_name=mod_name,
                provider=prov_name,
                retrieval_method=context.retrieval_method,
                generation_metadata={"reason": "insufficient_evidence_threshold"},
                warnings=all_warnings + ["Insufficient evidence threshold not met."],
            )
            self._persist_answer(insufficient_answer, ticker=request.ticker)
            return insufficient_answer

        # 3. Check LLM Provider Health / Availability
        is_healthy = self.llm_provider.health_check()
        if not is_healthy:
            offline_msg = (
                f"The configured LLM provider '{prov_name}' "
                f"(model '{mod_name}') is currently unreachable or offline. "
                f"Evidence was successfully retrieved ({len(context.retrieved_evidence)} passage(s), "
                f"{len(context.calculation_evidence)} calculation(s))."
            )
            logger.warning(
                "LLM provider '%s' is offline for answer_id=%s", prov_name, answer_id
            )
            offline_answer = RAGAnswer(
                answer_id=answer_id,
                question=request.question,
                answer=offline_msg,
                answer_status="provider_unavailable",
                citations=[],
                retrieved_evidence=context.retrieved_evidence,
                calculation_evidence=context.calculation_evidence,
                model_name=mod_name,
                provider=prov_name,
                retrieval_method=context.retrieval_method,
                generation_metadata={"error": "provider_health_check_failed"},
                warnings=all_warnings + ["LLM provider health check failed."],
            )
            self._persist_answer(offline_answer, ticker=request.ticker)
            return offline_answer

        # 4. Construct Grounding Prompts
        system_prompt, user_prompt = build_rag_prompts(
            question=request.question,
            context_text=context.prompt_context_text,
            response_style=request.response_style,
        )

        # 5. Execute LLM Generation
        t0 = time.perf_counter()
        try:
            gen_resp = self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.settings.LLM_TEMPERATURE,
                max_tokens=self.settings.LLM_MAX_TOKENS,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            logger.error("LLM generation error for answer_id=%s: %s", answer_id, exc)
            failed_answer = RAGAnswer(
                answer_id=answer_id,
                question=request.question,
                answer=f"Answer generation failed due to an error: {exc}",
                answer_status="generation_failed",
                citations=[],
                retrieved_evidence=context.retrieved_evidence,
                calculation_evidence=context.calculation_evidence,
                model_name=mod_name,
                provider=prov_name,
                retrieval_method=context.retrieval_method,
                generation_metadata={"error": str(exc)},
                warnings=all_warnings + [f"Generation error: {exc}"],
            )
            self._persist_answer(failed_answer, ticker=request.ticker)
            return failed_answer

        # 6. Validate Citations & Provenance
        val_result = self.citation_validator.validate_citations(
            answer_text=gen_resp.text,
            retrieved_evidence=context.retrieved_evidence,
            calculation_evidence=context.calculation_evidence,
        )
        all_warnings.extend(val_result.warnings)

        # 7. Determine Final Status
        answer_text_lower = gen_resp.text.lower()
        if (
            "insufficient evidence" in answer_text_lower
            or "do not provide sufficient" in answer_text_lower
            or "no sufficient information" in answer_text_lower
        ):
            answer_status = "insufficient_evidence"
        elif val_result.status == "verified":
            answer_status = "answered"
        elif val_result.status == "partially_supported":
            answer_status = "partially_supported"
        else:
            answer_status = "citation_validation_failed"

        metadata: dict[str, Any] = {
            "latency_ms": round(latency_ms, 2),
            "tokens_generated": gen_resp.tokens_generated,
            "prompt_tokens": gen_resp.prompt_tokens,
            "total_tokens": gen_resp.total_tokens,
            "temperature": self.settings.LLM_TEMPERATURE,
            "top_k": request.top_k,
            "used_reranker": request.use_reranker,
            "included_calculations": request.include_calculations,
        }
        if gen_resp.metadata:
            metadata.update(gen_resp.metadata)

        # 8. Post-Generation Anti-Hallucination & Claim-Level Verification
        verification_run_id: str | None = None
        verification_status: str | None = None
        if self.settings.VERIFICATION_ENABLED:
            try:
                v_run = self.verification_service.verify_answer(
                    answer_id=answer_id,
                    question=request.question,
                    answer_text=gen_resp.text.strip(),
                    retrieved_evidence=context.retrieved_evidence,
                    calculation_evidence=context.calculation_evidence,
                    persist=True,
                )
                verification_run_id = v_run.run_id
                verification_status = v_run.overall_status.value
                if v_run.warnings:
                    all_warnings.extend(v_run.warnings)
                if v_run.overall_status.value == "rejected":
                    answer_status = "verification_rejected"
                elif (
                    v_run.overall_status.value == "partially_verified"
                    and answer_status == "answered"
                ):
                    answer_status = "partially_verified"
            except Exception as exc:
                logger.warning("Verification failed for answer %s: %s", answer_id, exc)
                all_warnings.append(f"Verification execution error: {exc}")

        # 9. Assemble RAGAnswer Container
        final_answer = RAGAnswer(
            answer_id=answer_id,
            question=request.question,
            answer=gen_resp.text.strip(),
            answer_status=answer_status,
            citations=val_result.citations,
            retrieved_evidence=context.retrieved_evidence,
            calculation_evidence=context.calculation_evidence,
            model_name=mod_name,
            provider=prov_name,
            retrieval_method=context.retrieval_method,
            generation_metadata=metadata,
            verification_run_id=verification_run_id,
            verification_status=verification_status,
            warnings=all_warnings,
        )

        # 10. Persist to SQLite
        self._persist_answer(final_answer, ticker=request.ticker)
        return final_answer

    def get_answer(self, answer_id: str) -> RAGAnswer | None:
        """Retrieve previously saved research answer by identifier."""
        data = self.db.get_research_answer(answer_id)
        if not data:
            return None
        return RAGAnswer.model_validate(data)

    def get_capabilities(self) -> RAGCapabilitiesResponse:
        """Report active operational capabilities of the RAG pipeline."""
        llm_online = self.llm_provider.health_check()
        return RAGCapabilitiesResponse(
            supported_retrieval_modes=["dense", "sparse", "hybrid", "hybrid_reranked"],
            reranker_available=True,
            reranker_model=self.settings.RERANKER_MODEL_NAME,
            calculation_engine_enabled=True,
            citation_verification_enabled=True,
            verification_engine_enabled=self.settings.VERIFICATION_ENABLED,
            verification_version=self.settings.VERIFICATION_VERSION,
            llm_provider=self.llm_provider.provider_name,
            llm_model=self.llm_provider.model_name,
            llm_online=llm_online,
        )

    def _persist_answer(self, answer: RAGAnswer, ticker: str | None = None) -> None:
        """Safely persist answer payload to SQLite storage."""
        try:
            payload = answer.model_dump()
            if ticker and not payload.get("ticker"):
                payload["ticker"] = ticker
            self.db.save_research_answer(payload)
        except Exception as exc:
            logger.warning(
                "Failed to persist research answer %s: %s", answer.answer_id, exc
            )
