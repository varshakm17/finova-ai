"""Anti-Hallucination & Claim-Level Answer Verification Module for Finova AI."""

from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.contradiction_detector import ContradictionDetector
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.numeric_verifier import NumericVerifier
from backend.verification.period_verifier import PeriodVerifier
from backend.verification.verification_models import (
    ClaimExtractionResult,
    ClaimType,
    ClaimVerificationResult,
    ContradictionDetail,
    ExtractedClaim,
    NumericClaimValue,
    NumericVerificationDetail,
    OverallVerificationStatus,
    PeriodVerificationDetail,
    VerificationOutcome,
    VerificationRun,
)
from backend.verification.verification_service import VerificationService

__all__ = [
    "ClaimExtractionResult",
    "ClaimExtractor",
    "ClaimType",
    "ClaimVerificationResult",
    "ContradictionDetail",
    "ContradictionDetector",
    "EvidenceVerifier",
    "ExtractedClaim",
    "NumericClaimValue",
    "NumericVerificationDetail",
    "NumericVerifier",
    "OverallVerificationStatus",
    "PeriodVerificationDetail",
    "PeriodVerifier",
    "VerificationOutcome",
    "VerificationRun",
    "VerificationService",
]
