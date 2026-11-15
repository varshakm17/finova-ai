"""Verification Service Orchestrator for Finova AI.

Coordinates claim extraction, evidence-to-claim support auditing, numerical verification,
period consistency checking, and contradiction detection to render an aggregate verification verdict.
"""

from __future__ import annotations

import uuid

from backend.data.storage import Database
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.contradiction_detector import ContradictionDetector
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.verification_models import (
    ClaimVerificationResult,
    ContradictionDetail,
    NumericVerificationDetail,
    OverallVerificationStatus,
    PeriodVerificationDetail,
    VerificationOutcome,
    VerificationRun,
)
from config.settings import Settings, get_settings

logger = get_logger("verification_service")


class VerificationService:
    """Orchestrates end-to-end anti-hallucination and claim-level verification."""

    def __init__(
        self,
        claim_extractor: ClaimExtractor | None = None,
        evidence_verifier: EvidenceVerifier | None = None,
        contradiction_detector: ContradictionDetector | None = None,
        database: Database | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = database or Database()
        self.claim_extractor = claim_extractor or ClaimExtractor()
        self.contradiction_detector = contradiction_detector or ContradictionDetector()
        self.evidence_verifier = evidence_verifier or EvidenceVerifier(
            contradiction_detector=self.contradiction_detector,
            settings=self.settings,
        )
        self.verifier_version = getattr(self.settings, "VERIFICATION_VERSION", "0.1.0")

    def verify_answer(
        self,
        answer_id: str,
        question: str,
        answer_text: str,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
        persist: bool = True,
    ) -> VerificationRun:
        """Execute comprehensive claim-level verification over generated answer.

        Args:
            answer_id: Identifier of the answer being evaluated.
            question: Original research question.
            answer_text: Generated answer text.
            retrieved_evidence: Statutory filing passages in context.
            calculation_evidence: Deterministic calculation receipts in context.

        Returns:
            VerificationRun containing aggregate verdict, claim results, and issue audits.
        """
        run_id = f"vrun_{uuid.uuid4().hex[:12]}"
        logger.info(
            "Initiating verification run=%s for answer_id=%s (claims extraction)...",
            run_id,
            answer_id,
        )

        # 1. Extract Atomic Claims
        extraction_res = self.claim_extractor.extract_claims(
            text=answer_text,
            answer_id=answer_id,
        )
        claims = extraction_res.claims

        # 2. Check for Cross-Evidence Contradictions
        cross_contradictions = (
            self.contradiction_detector.detect_cross_evidence_contradictions(
                retrieved_evidence=retrieved_evidence
            )
        )

        # 3. Verify Every Claim Individually
        claim_results: list[ClaimVerificationResult] = []
        all_warnings: list[str] = []
        contradictions: list[ContradictionDetail] = list(cross_contradictions)
        numeric_mismatches: list[NumericVerificationDetail] = []
        period_mismatches: list[PeriodVerificationDetail] = []

        for claim in claims:
            res = self.evidence_verifier.verify_claim(
                claim=claim,
                retrieved_evidence=retrieved_evidence,
                calculation_evidence=calculation_evidence,
            )
            claim_results.append(res)
            all_warnings.extend(res.warnings)

            if res.contradiction_check and res.contradiction_check.has_contradiction:
                contradictions.append(res.contradiction_check)

            if res.numeric_check and not res.numeric_check.matched:
                numeric_mismatches.append(res.numeric_check)

            if res.period_check and not res.period_check.is_consistent:
                period_mismatches.append(res.period_check)

        # 4. Count Outcomes
        total_claims = len(claim_results)
        supported_count = sum(
            1 for cr in claim_results if cr.outcome == VerificationOutcome.SUPPORTED
        )
        partially_supported_count = sum(
            1
            for cr in claim_results
            if cr.outcome == VerificationOutcome.PARTIALLY_SUPPORTED
        )
        unsupported_count = sum(
            1 for cr in claim_results if cr.outcome == VerificationOutcome.UNSUPPORTED
        )
        contradicted_count = sum(
            1 for cr in claim_results if cr.outcome == VerificationOutcome.CONTRADICTED
        )
        not_verifiable_count = sum(
            1
            for cr in claim_results
            if cr.outcome == VerificationOutcome.NOT_VERIFIABLE
        )

        # 5. Deterministic Overall Decision Logic
        if contradicted_count > 0 or any(
            c.has_contradiction for c in cross_contradictions
        ):
            overall_status = OverallVerificationStatus.REJECTED
            all_warnings.append(
                f"Verification REJECTED: {contradicted_count} claim(s) or cross-evidence passages directly contradict verified facts."
            )
        elif supported_count == 0 and unsupported_count > 0:
            overall_status = OverallVerificationStatus.REJECTED
            all_warnings.append(
                "Verification REJECTED: Zero claims were supported by cited evidence."
            )
        elif (
            unsupported_count == 0
            and partially_supported_count == 0
            and supported_count > 0
        ):
            if all_warnings or period_mismatches or numeric_mismatches:
                overall_status = OverallVerificationStatus.VERIFIED_WITH_WARNINGS
            else:
                overall_status = OverallVerificationStatus.VERIFIED
        elif supported_count > 0 and (
            unsupported_count > 0 or partially_supported_count > 0
        ):
            overall_status = OverallVerificationStatus.PARTIALLY_VERIFIED
            all_warnings.append(
                f"Partial verification: {supported_count}/{total_claims} claims supported; "
                f"{unsupported_count} unsupported, {partially_supported_count} partially supported."
            )
        else:
            overall_status = OverallVerificationStatus.INCONCLUSIVE
            all_warnings.append(
                "Verification INCONCLUSIVE: Insufficient verifiable assertions in response."
            )

        vrun = VerificationRun(
            run_id=run_id,
            answer_id=answer_id,
            overall_status=overall_status,
            total_claims=total_claims,
            supported_claims=supported_count,
            partially_supported_claims=partially_supported_count,
            unsupported_claims=unsupported_count,
            contradicted_claims=contradicted_count,
            not_verifiable_claims=not_verifiable_count,
            claim_results=claim_results,
            contradictions=contradictions,
            numeric_mismatches=numeric_mismatches,
            period_mismatches=period_mismatches,
            warnings=all_warnings,
            verifier_version=self.verifier_version,
        )

        # 6. Relational Persistence
        if persist:
            try:
                self.db.save_verification_run(vrun.model_dump())
                logger.info(
                    "Verification run %s persisted for answer %s.", run_id, answer_id
                )
            except Exception as exc:
                logger.warning("Failed to persist verification run %s: %s", run_id, exc)

        return vrun

    def get_verification_run(self, run_id: str) -> VerificationRun | None:
        """Fetch previously stored verification run by identifier."""
        data = self.db.get_verification_run(run_id)
        if not data:
            return None
        return VerificationRun.model_validate(data)

    def get_latest_verification_for_answer(
        self, answer_id: str
    ) -> VerificationRun | None:
        """Fetch the most recent verification run for a given answer_id."""
        data = self.db.get_latest_verification_for_answer(answer_id)
        if not data:
            return None
        return VerificationRun.model_validate(data)
