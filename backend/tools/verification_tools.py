"""Verification and anti-hallucination tools for Finova AI agents."""

from __future__ import annotations

import uuid
from typing import Any

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.verification_service import VerificationService

logger = get_logger("verification_tools")


def extract_claims_tool(
    text: str,
    extractor: ClaimExtractor | None = None,
) -> list[dict[str, Any]]:
    """Extract verifiable factual and numerical claims from answer text."""
    ex = extractor or ClaimExtractor()
    result = ex.extract_claims(text=text, answer_id=str(uuid.uuid4()))
    return [c.model_dump() for c in result.claims]


def verify_answer_tool(
    question: str,
    answer_text: str,
    retrieved_evidence: list[dict[str, Any]],
    calculation_evidence: list[dict[str, Any]],
    verifier: VerificationService | None = None,
) -> dict[str, Any]:
    """Execute claim-level verification against provided evidence passages and calculation receipts."""
    service = verifier or VerificationService()

    retrieved_objs = [
        RetrievedEvidence(
            evidence_id=f"E{idx}",
            chunk_id=str(ev.get("chunk_id", f"c_{idx}")),
            ticker=str(ev.get("ticker", "AAPL")),
            company_name=str(ev.get("company_name", "Target")),
            filing_type=str(ev.get("filing_type", "10-K")),
            filing_date=str(ev.get("filing_date", "2023-11-03")),
            accession_number=str(ev.get("accession_number", "0000320193-23-000106")),
            section_identifier=str(ev.get("section_identifier", "ITEM_7")),
            section_title=str(ev.get("section_title", "Disclosures")),
            chunk_text=str(ev.get("text") or ev.get("chunk_text", "")),
            source_url=str(ev.get("source_url", "https://www.sec.gov")),
        )
        for idx, ev in enumerate(retrieved_evidence, start=1)
    ]

    calc_objs = [
        CalculationEvidence(
            evidence_id=f"C{idx}",
            calculation_id=str(ce.get("calculation_id", f"calc_{idx}")),
            metric_name=str(ce.get("metric_name", "Metric")),
            calculated_value=float(ce.get("calculated_value", 0.0)),
            unit=str(ce.get("unit", "ratio")),
            formula=str(ce.get("formula_definition") or ce.get("formula", "N/A")),
            period_end=str(ce.get("period_end", "2023-09-30")),
        )
        for idx, ce in enumerate(calculation_evidence, start=1)
    ]

    res = service.verify_answer(
        answer_id=str(uuid.uuid4()),
        question=question,
        answer_text=answer_text,
        retrieved_evidence=retrieved_objs,
        calculation_evidence=calc_objs,
        persist=False,
    )
    return res.model_dump()
