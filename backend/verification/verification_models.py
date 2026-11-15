"""Pydantic models and schemas for Anti-Hallucination & Claim-Level Answer Verification."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Categorical classification of independently extracted assertions."""

    FINANCIAL_METRIC = "financial_metric"
    HISTORICAL_COMPARISON = "historical_comparison"
    TREND_DIRECTION = "trend_direction"
    FORWARD_LOOKING = "forward_looking"
    RISK_OR_BUSINESS = "risk_or_business"
    PERFORMANCE_STATEMENT = "performance_statement"
    GENERAL_FACT = "general_fact"


class VerificationOutcome(str, Enum):
    """Structured verdict for claim-to-evidence support auditing."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_VERIFIABLE = "not_verifiable"


class OverallVerificationStatus(str, Enum):
    """Holistic assessment of generated financial answer fidelity."""

    VERIFIED = "verified"
    VERIFIED_WITH_WARNINGS = "verified_with_warnings"
    PARTIALLY_VERIFIED = "partially_verified"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class NumericClaimValue(BaseModel):
    """Parsed numerical entity within a financial claim."""

    raw_text: str = Field(..., description="Verbatim numerical snippet from claim text")
    numeric_value: float = Field(..., description="Parsed floating-point value")
    unit: str | None = Field(
        default=None, description="Associated unit (e.g. 'USD', '%', 'ratio')"
    )
    metric_name: str | None = Field(
        default=None, description="Inferred canonical financial metric"
    )
    scale_multiplier: float = Field(
        default=1.0, description="Scale factor applied (e.g. 1e9 for billion)"
    )
    normalized_value: float | None = Field(
        default=None, description="Absolute base value after scale"
    )
    is_percentage: bool = Field(
        default=False, description="Whether the entity is a percentage"
    )
    period: str | None = Field(
        default=None, description="Associated fiscal period if present"
    )


class ExtractedClaim(BaseModel):
    """Independently verifiable financial or qualitative assertion."""

    claim_id: str = Field(..., description="Unique claim identifier (e.g. 'CLM-01')")
    claim_text: str = Field(..., description="Normalized text of the extracted claim")
    claim_type: ClaimType = Field(
        default=ClaimType.GENERAL_FACT, description="Category of assertion"
    )
    numeric_values: list[NumericClaimValue] = Field(
        default_factory=list,
        description="Quantitative figures extracted from the claim",
    )
    mentioned_company: str | None = Field(
        default=None, description="Target company ticker or name"
    )
    mentioned_period: str | None = Field(
        default=None, description="Fiscal reporting period (e.g. 'FY2023')"
    )
    citation_ids: list[str] = Field(
        default_factory=list,
        description="Associated citation tags from answer context (e.g. ['E1', 'C1'])",
    )
    is_verifiable: bool = Field(
        default=True, description="Whether the claim is objectively verifiable"
    )
    start_char: int | None = Field(
        default=None, description="Character offset in original text"
    )
    end_char: int | None = Field(
        default=None, description="End character offset in original text"
    )


class ClaimExtractionResult(BaseModel):
    """Container holding all claims extracted from an answer."""

    answer_id: str = Field(..., description="Associated answer identifier")
    original_text: str = Field(..., description="Full original generated answer text")
    claims: list[ExtractedClaim] = Field(
        default_factory=list, description="Extracted claims list"
    )
    extraction_method: str = Field(
        default="deterministic_rule_based", description="Parser method used"
    )


class NumericVerificationDetail(BaseModel):
    """Diagnostic audit trail for quantitative value verification."""

    matched: bool = Field(
        ..., description="Whether claimed value matched verified source"
    )
    claimed_value: float | None = Field(
        default=None, description="Value extracted from claim"
    )
    source_value: float | None = Field(
        default=None, description="Value from statutory source or receipt"
    )
    claimed_unit: str | None = Field(default=None, description="Unit stated in claim")
    source_unit: str | None = Field(
        default=None, description="Unit in statutory source or receipt"
    )
    error_type: str | None = Field(
        default=None,
        description="Type of numerical mismatch: 'scale_error_thousands_vs_millions', "
        "'scale_error_percentage_vs_fraction', 'sign_mismatch', 'value_mismatch', 'none'",
    )
    discrepancy_details: str = Field(
        default="", description="Human-readable explanation of check"
    )
    tolerance_pct_applied: float = Field(
        default=1.0, description="Allowed percentage tolerance"
    )


class PeriodVerificationDetail(BaseModel):
    """Audit findings for temporal reporting period consistency."""

    is_consistent: bool = Field(
        ..., description="Whether claim period matches source evidence period"
    )
    claimed_period: str | None = Field(
        default=None, description="Period mentioned in claim"
    )
    source_period: str | None = Field(
        default=None, description="Period established in evidence provenance"
    )
    mismatch_type: str | None = Field(
        default=None,
        description="Classification: 'fiscal_year_mismatch', 'annual_vs_quarterly', "
        "'quarter_mismatch', 'calendar_vs_fiscal', 'none'",
    )
    explanation: str = Field(default="", description="Audit explanation")


class ContradictionDetail(BaseModel):
    """Report on opposing evidence or factual divergence."""

    has_contradiction: bool = Field(
        ..., description="Whether a direct contradiction was identified"
    )
    contradicting_evidence_id: str | None = Field(
        default=None, description="Evidence ID containing contradiction"
    )
    contradiction_type: str | None = Field(
        default=None,
        description="Classification: 'numerical_conflict', 'directional_conflict', 'temporal_conflict', 'none'",
    )
    claimed_statement: str = Field(default="", description="Claim text or direction")
    evidence_statement: str = Field(
        default="", description="Conflicting evidence text or value"
    )
    explanation: str = Field(
        default="", description="Explanation of why this constitutes a contradiction"
    )


class ClaimVerificationResult(BaseModel):
    """Comprehensive verification verdict and audit for a single claim."""

    claim_id: str = Field(..., description="Evaluated claim identifier")
    claim_text: str = Field(..., description="Text of evaluated claim")
    outcome: VerificationOutcome = Field(..., description="Verdict")
    supporting_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs confirming the claim",
    )
    contradicting_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Evidence IDs directly disputing the claim",
    )
    verification_reason: str = Field(
        ..., description="Detailed explanation of verification outcome"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Deterministic verification confidence score (heuristic score, NOT statistical probability)",
    )
    verification_method: str = Field(
        ...,
        description="Method applied (e.g. 'deterministic_receipt', 'lexical_overlap')",
    )
    numeric_check: NumericVerificationDetail | None = Field(
        default=None, description="Numerical check findings"
    )
    period_check: PeriodVerificationDetail | None = Field(
        default=None, description="Period check findings"
    )
    contradiction_check: ContradictionDetail | None = Field(
        default=None, description="Contradiction check findings"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Claim-level warnings"
    )


class VerificationRun(BaseModel):
    """Complete audit report covering all claims of an answer."""

    run_id: str = Field(..., description="Unique verification execution run identifier")
    answer_id: str = Field(..., description="Answer identifier evaluated")
    overall_status: OverallVerificationStatus = Field(
        ..., description="Aggregate verification verdict"
    )
    total_claims: int = Field(default=0, description="Total claims extracted")
    supported_claims: int = Field(
        default=0, description="Count of fully supported claims"
    )
    partially_supported_claims: int = Field(
        default=0, description="Count of partially supported claims"
    )
    unsupported_claims: int = Field(
        default=0, description="Count of unsupported claims"
    )
    contradicted_claims: int = Field(
        default=0, description="Count of contradicted claims"
    )
    not_verifiable_claims: int = Field(
        default=0, description="Count of unverified claims"
    )
    claim_results: list[ClaimVerificationResult] = Field(
        default_factory=list,
        description="Itemized claim evaluation results",
    )
    contradictions: list[ContradictionDetail] = Field(
        default_factory=list,
        description="All detected evidence or claim contradictions",
    )
    numeric_mismatches: list[NumericVerificationDetail] = Field(
        default_factory=list,
        description="All numerical calculation or value mismatches",
    )
    period_mismatches: list[PeriodVerificationDetail] = Field(
        default_factory=list,
        description="All reporting period inconsistencies",
    )
    warnings: list[str] = Field(
        default_factory=list, description="Aggregate execution and audit warnings"
    )
    verified_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 execution timestamp",
    )
    verifier_version: str = Field(
        default="0.1.0", description="Verification engine version"
    )
