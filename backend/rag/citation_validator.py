"""Citation validator and provenance auditor for Evidence-Grounded Financial RAG.

Extracts evidence citations ([E1], [C1]) from generated answers, verifies their
presence in the prompt context, maps citations to statutory source URLs and excerpts,
and audits for fabricated or unsupported claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from backend.rag.rag_models import (
    CalculationEvidence,
    Citation,
    RetrievedEvidence,
)
from backend.utils.logger import get_logger

logger = get_logger("citation_validator")

# Regex to capture bracketed citation tags: [E1], [C2], [E1, E2], [E1, C1], [E1][C1]
CITATION_TAG_PATTERN = re.compile(r"\[([EC]\d+(?:\s*,\s*[EC]\d+)*)\]", re.IGNORECASE)
SINGLE_CITATION_PATTERN = re.compile(r"\b([EC]\d+)\b", re.IGNORECASE)


@dataclass
class CitationValidationResult:
    """Audit report from citation verification over generated financial answer text."""

    citations: list[Citation] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    unsupported_ids: list[str] = field(default_factory=list)
    is_valid: bool = True
    status: Literal["verified", "partially_supported", "citation_validation_failed"] = (
        "verified"
    )
    warnings: list[str] = field(default_factory=list)


class CitationValidator:
    """Verifies that generated answers cite only available, verified statutory evidence."""

    def __init__(self, excerpt_max_chars: int = 250) -> None:
        self.excerpt_max_chars = excerpt_max_chars

    def extract_citation_ids(self, text: str) -> list[str]:
        """Extract unique citation identifiers in order of appearance from text.

        Supports bracketed formats like [E1], [C1], [E1, E2], [E1, C2].
        """
        if not text:
            return []

        found_ids: list[str] = []
        seen: set[str] = set()

        matches = CITATION_TAG_PATTERN.findall(text)
        for match in matches:
            # Match may be comma-separated like "E1, E2"
            parts = SINGLE_CITATION_PATTERN.findall(match)
            for part in parts:
                normalized_id = part.upper()
                if normalized_id not in seen:
                    seen.add(normalized_id)
                    found_ids.append(normalized_id)

        return found_ids

    def validate_citations(
        self,
        answer_text: str,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
    ) -> CitationValidationResult:
        """Verify citations in answer text against supplied retrieved & calculation evidence.

        Args:
            answer_text: Synthesized answer string from the LLM.
            retrieved_evidence: Validated document passages supplied in prompt context.
            calculation_evidence: Deterministic calculation receipts supplied in prompt context.

        Returns:
            CitationValidationResult with verified citations, unsupported IDs, and warnings.
        """
        cited_ids = self.extract_citation_ids(answer_text)
        warnings: list[str] = []

        # Index available evidence
        retrieved_map: dict[str, RetrievedEvidence] = {
            ev.evidence_id.upper(): ev for ev in retrieved_evidence
        }
        calc_map: dict[str, CalculationEvidence] = {
            ev.evidence_id.upper(): ev for ev in calculation_evidence
        }
        all_available_ids = set(retrieved_map.keys()) | set(calc_map.keys())

        verified_citations: list[Citation] = []
        unsupported_ids: list[str] = []

        for cid in cited_ids:
            if cid in retrieved_map:
                rev = retrieved_map[cid]
                ref_section = (
                    rev.section_identifier or rev.section_title or "Disclosure"
                )
                source_ref = (
                    f"{rev.ticker} {rev.filing_type} ({rev.filing_date}) {ref_section}"
                )
                excerpt = rev.chunk_text.strip()
                if len(excerpt) > self.excerpt_max_chars:
                    excerpt = excerpt[: self.excerpt_max_chars].rstrip() + "..."

                verified_citations.append(
                    Citation(
                        citation_id=cid,
                        evidence_type="filing_passage",
                        source_reference=source_ref,
                        source_url=rev.source_url,
                        excerpt=excerpt,
                    )
                )
            elif cid in calc_map:
                cev = calc_map[cid]
                source_ref = (
                    f"Deterministic Calc: {cev.metric_name} ({cev.period_end}) = "
                    f"{cev.calculated_value:,.2f} {cev.unit}".strip()
                )
                excerpt = f"Formula: {cev.formula}"
                verified_citations.append(
                    Citation(
                        citation_id=cid,
                        evidence_type="calculation_receipt",
                        source_reference=source_ref,
                        source_url="https://www.sec.gov/edgar",
                        excerpt=excerpt,
                    )
                )
            else:
                unsupported_ids.append(cid)

        # Audit findings
        if unsupported_ids:
            msg = f"Answer references unsupported citation identifier(s): {', '.join(unsupported_ids)}"
            warnings.append(msg)
            logger.warning(msg)

        has_available_context = bool(all_available_ids)
        is_insufficient_evidence_response = (
            "insufficient evidence" in answer_text.lower()
            or "do not provide sufficient" in answer_text.lower()
            or "no sufficient information" in answer_text.lower()
        )

        status: Literal[
            "verified", "partially_supported", "citation_validation_failed"
        ] = "verified"
        is_valid = True

        if unsupported_ids:
            if verified_citations:
                status = "partially_supported"
                is_valid = False
            else:
                status = "citation_validation_failed"
                is_valid = False
        elif not cited_ids:
            if has_available_context and not is_insufficient_evidence_response:
                # Substantial factual text was produced without any citations
                msg = (
                    "Answer contains factual text but zero verified evidence citations."
                )
                warnings.append(msg)
                logger.warning(msg)
                status = "partially_supported"
            else:
                status = "verified"
        else:
            status = "verified"

        return CitationValidationResult(
            citations=verified_citations,
            cited_ids=cited_ids,
            unsupported_ids=unsupported_ids,
            is_valid=is_valid,
            status=status,
            warnings=warnings,
        )
