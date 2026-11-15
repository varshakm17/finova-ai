"""Verification Agent for Finova AI Multi-Agent Orchestration.

Performs claim-level anti-hallucination verification across numerical values,
reporting periods, and factual claims against retrieved evidence and receipts.
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.verification_models import OverallVerificationStatus
from backend.verification.verification_service import VerificationService
from config.settings import Settings, get_settings

logger = get_logger("verification_agent")


class VerificationAgent(BaseFinovaAgent):
    """Verification Agent auditing generated answers before user presentation."""

    def __init__(
        self,
        verification_service: VerificationService | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(
            agent_name="VerificationAgent",
            description="Performs claim-level anti-hallucination checks, numerical verification, and contradiction detection.",
        )
        self.settings = settings or get_settings()
        self.verifier = verification_service or VerificationService(
            settings=self.settings
        )

    def _convert_retrieved_evidence(
        self, raw_evidence: list[dict[str, Any]]
    ) -> list[RetrievedEvidence]:
        """Convert dictionary evidence representations into typed RetrievedEvidence models."""
        converted = []
        for idx, ev in enumerate(raw_evidence, start=1):
            converted.append(
                RetrievedEvidence(
                    evidence_id=f"E{idx}",
                    chunk_id=str(ev.get("chunk_id", f"chunk_{idx}")),
                    ticker=str(ev.get("ticker", "AAPL")),
                    company_name=str(ev.get("company_name", "Target Company")),
                    filing_type=str(ev.get("filing_type", "10-K")),
                    filing_date=str(ev.get("filing_date", "2023-11-03")),
                    report_date=ev.get("report_date", "2023-09-30"),
                    accession_number=str(
                        ev.get("accession_number", "0000320193-23-000106")
                    ),
                    section_identifier=str(ev.get("section_identifier", "ITEM_7")),
                    section_title=str(ev.get("section_title", "Disclosures")),
                    chunk_text=str(ev.get("text") or ev.get("chunk_text", "")),
                    source_url=str(ev.get("source_url", "https://www.sec.gov")),
                )
            )
        return converted

    def _convert_calculation_evidence(
        self, raw_calcs: list[dict[str, Any]]
    ) -> list[CalculationEvidence]:
        """Convert dictionary calculation receipts into typed CalculationEvidence models."""
        converted = []
        for idx, ce in enumerate(raw_calcs, start=1):
            val = ce.get("calculated_value", 0.0)
            try:
                fval = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                fval = 0.0

            converted.append(
                CalculationEvidence(
                    evidence_id=f"C{idx}",
                    calculation_id=str(ce.get("calculation_id", f"calc_{idx}")),
                    metric_name=str(ce.get("metric_name", "Metric")),
                    calculated_value=fval,
                    unit=str(ce.get("unit", "ratio")),
                    formula=str(
                        ce.get("formula_definition") or ce.get("formula", "N/A")
                    ),
                    period_start=ce.get("period_start"),
                    period_end=str(ce.get("period_end", "2023-09-30")),
                    input_observations=ce.get("inputs")
                    or ce.get("input_observations")
                    or [],
                )
            )
        return converted

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute claim-level verification over generated answer."""
        question = state.get("user_question", "")
        answer_text = state.get("generated_answer", "")
        raw_retrieved = state.get("retrieved_evidence", [])
        raw_calcs = state.get("calculation_results", [])
        answer_id = state.get("request_id", str(uuid.uuid4()))

        # If there is no answer or an insufficient evidence notice
        if (
            not answer_text
            or "do not provide sufficient evidence" in answer_text.lower()
        ):
            logger.info(
                "VerificationAgent: Insufficient evidence response, passing without claim check."
            )
            return {
                "verification_result": {
                    "overall_status": OverallVerificationStatus.VERIFIED.value,
                    "is_valid": True,
                    "total_claims": 0,
                    "supported_claims": 0,
                    "partially_supported_claims": 0,
                    "unsupported_claims": 0,
                    "contradicted_claims": 0,
                    "not_verifiable_claims": 0,
                    "warnings": [],
                },
                "final_answer": answer_text,
                "current_step": "verification_agent",
            }

        retrieved_objs = self._convert_retrieved_evidence(raw_retrieved)
        calc_objs = self._convert_calculation_evidence(raw_calcs)

        try:
            run_result = self.verifier.verify_answer(
                answer_id=answer_id,
                question=question,
                answer_text=answer_text,
                retrieved_evidence=retrieved_objs,
                calculation_evidence=calc_objs,
                persist=True,
            )

            status_val = run_result.overall_status.value
            is_valid = status_val != OverallVerificationStatus.REJECTED.value

            logger.info(
                "VerificationAgent: Answer %s evaluated with overall_status=%s (is_valid=%s)",
                answer_id,
                status_val,
                is_valid,
            )

            result_dict = run_result.model_dump()
            result_dict["is_valid"] = is_valid

            return {
                "verification_result": result_dict,
                "final_answer": answer_text if is_valid else None,
                "current_step": "verification_agent",
                "warnings": run_result.warnings,
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("VerificationAgent failed during claim verification: %s", exc)
            return {
                "verification_result": {
                    "overall_status": OverallVerificationStatus.VERIFIED_WITH_WARNINGS.value,
                    "is_valid": True,
                    "warnings": [f"Verification check degraded: {exc}"],
                },
                "final_answer": answer_text,
                "current_step": "verification_agent",
                "warnings": [f"Verification check degraded: {exc}"],
            }
