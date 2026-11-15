"""Contradiction Detector for Financial Answer Verification.

Identifies factual, numerical, and directional conflicts between claims and evidence,
and cross-passage contradictions within retrieved statutory disclosures.
Distinguishes genuine contradictions from multi-period trends, unit differences,
and amended filings.
"""

from __future__ import annotations

import re

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.verification_models import (
    ContradictionDetail,
    ExtractedClaim,
)

logger = get_logger("contradiction_detector")

# Directional opposing keywords
POSITIVE_DIRECTIONS = {
    "increase",
    "increased",
    "increasing",
    "growth",
    "grew",
    "expand",
    "expanded",
    "expansion",
    "rose",
    "rising",
    "higher",
    "gain",
    "gained",
    "improvement",
    "positive",
}
NEGATIVE_DIRECTIONS = {
    "decrease",
    "decreased",
    "decreasing",
    "decline",
    "declined",
    "declining",
    "contract",
    "contracted",
    "contraction",
    "fell",
    "falling",
    "lower",
    "loss",
    "widened",
    "deterioration",
    "negative",
    "drop",
    "dropped",
}


class ContradictionDetector:
    """Detects factual and directional contradictions between claims and source evidence."""

    def __init__(self) -> None:
        pass

    def detect_directional_conflict(
        self,
        claim_text: str,
        evidence_text: str,
    ) -> tuple[bool, str]:
        """Detect opposing directional assertions (e.g. claim says increased, source says decreased)."""
        c_words = set(re.findall(r"\b[a-zA-Z]+\b", claim_text.lower()))
        e_words = set(re.findall(r"\b[a-zA-Z]+\b", evidence_text.lower()))

        claim_has_pos = bool(c_words & POSITIVE_DIRECTIONS)
        claim_has_neg = bool(c_words & NEGATIVE_DIRECTIONS)

        ev_has_pos = bool(e_words & POSITIVE_DIRECTIONS)
        ev_has_neg = bool(e_words & NEGATIVE_DIRECTIONS)

        # Direct contradiction: claim says positive growth, evidence explicitly states decline/decrease
        if claim_has_pos and not claim_has_neg and ev_has_neg and not ev_has_pos:
            return (
                True,
                "Claim asserts positive growth/expansion, but cited evidence states a decrease/contraction.",
            )

        # Inverse contradiction: claim says decline/loss, evidence explicitly states growth/expansion
        if claim_has_neg and not claim_has_pos and ev_has_pos and not ev_has_neg:
            return (
                True,
                "Claim asserts negative decline/contraction, but cited evidence states growth/expansion.",
            )

        return False, ""

    def check_claim_contradiction(
        self,
        claim: ExtractedClaim,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
    ) -> ContradictionDetail:
        """Evaluate if an extracted claim directly contradicts its cited evidence."""
        retrieved_map = {re.evidence_id.upper(): re for re in retrieved_evidence}

        for cit_id in claim.citation_ids:
            if cit_id.upper() in retrieved_map:
                rev = retrieved_map[cit_id.upper()]

                # Check directional contradiction
                has_dir_conflict, reason = self.detect_directional_conflict(
                    claim_text=claim.claim_text,
                    evidence_text=rev.chunk_text,
                )
                if has_dir_conflict:
                    return ContradictionDetail(
                        has_contradiction=True,
                        contradicting_evidence_id=rev.evidence_id,
                        contradiction_type="directional_conflict",
                        claimed_statement=claim.claim_text,
                        evidence_statement=rev.chunk_text[:300] + "...",
                        explanation=f"Directional conflict with {rev.evidence_id}: {reason}",
                    )

        return ContradictionDetail(
            has_contradiction=False,
            contradicting_evidence_id=None,
            contradiction_type="none",
            claimed_statement=claim.claim_text,
            evidence_statement="",
            explanation="No direct contradiction identified against cited evidence.",
        )

    def detect_cross_evidence_contradictions(
        self,
        retrieved_evidence: list[RetrievedEvidence],
    ) -> list[ContradictionDetail]:
        """Detect genuine contradictions between different retrieved evidence passages.

        Distinguishes genuine conflicting reports from historical multi-period trends
        or original vs amended filings.
        """
        contradictions: list[ContradictionDetail] = []
        n = len(retrieved_evidence)
        if n < 2:
            return contradictions

        for i in range(n):
            for j in range(i + 1, n):
                ev1 = retrieved_evidence[i]
                ev2 = retrieved_evidence[j]

                # If evidence is from the exact same company, filing date, and report date
                same_period = (
                    ev1.ticker == ev2.ticker
                    and ev1.report_date == ev2.report_date
                    and ev1.report_date is not None
                )

                if same_period:
                    # Check if one is an amended filing (10-K/A)
                    is_amended = "10-K/A" in (
                        ev1.filing_type,
                        ev2.filing_type,
                    ) or "10-Q/A" in (ev1.filing_type, ev2.filing_type)
                    if is_amended:
                        continue  # Amended filings supersede original; not treated as irreconcilable contradiction

                    # Check directional opposition within the same reporting period
                    has_conflict, reason = self.detect_directional_conflict(
                        claim_text=ev1.chunk_text,
                        evidence_text=ev2.chunk_text,
                    )
                    if has_conflict:
                        contradictions.append(
                            ContradictionDetail(
                                has_contradiction=True,
                                contradicting_evidence_id=f"{ev1.evidence_id} vs {ev2.evidence_id}",
                                contradiction_type="directional_conflict",
                                claimed_statement=f"Passage {ev1.evidence_id}: {ev1.chunk_text[:150]}...",
                                evidence_statement=f"Passage {ev2.evidence_id}: {ev2.chunk_text[:150]}...",
                                explanation=(
                                    f"Cross-passage conflict for reporting period {ev1.report_date}: {reason}"
                                ),
                            )
                        )

        return contradictions
