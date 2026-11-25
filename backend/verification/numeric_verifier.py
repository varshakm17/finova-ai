"""Deterministic Numerical Claim Verification for Finova AI.

Performs exact and tolerance-based mathematical audits of quantitative claims
against retrieved statutory SEC filing evidence and deterministic XBRL calculation receipts.
Detects scale errors (thousands vs millions), unit confusion (percentages vs decimals),
sign inversions, and value discrepancies.
"""

from __future__ import annotations

import math
import re
from typing import Any

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.verification_models import (
    ExtractedClaim,
    NumericClaimValue,
    NumericVerificationDetail,
)
from config.settings import Settings, get_settings

logger = get_logger("numeric_verifier")


class NumericVerifier:
    """Audits numerical values in financial assertions against verified source evidence."""

    def __init__(
        self,
        tolerance_pct: float | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tolerance_pct = (
            tolerance_pct
            if tolerance_pct is not None
            else getattr(self.settings, "VERIFICATION_NUMERIC_TOLERANCE_PCT", 1.0)
        )

    def is_close_within_tolerance(
        self,
        val1: float,
        val2: float,
        tolerance_pct: float | None = None,
    ) -> bool:
        """Evaluate if two numbers are identical within a relative percentage threshold or presentation rounding."""
        tol = tolerance_pct if tolerance_pct is not None else self.tolerance_pct
        if math.isclose(val1, val2, abs_tol=1e-5):
            return True

        # Check standard 2-decimal-place presentation rounding (e.g. 0.22 vs 0.2229)
        if math.isclose(val1, round(val2, 2), abs_tol=1e-4) or math.isclose(
            round(val1, 2), val2, abs_tol=1e-4
        ):
            return True

        if abs(val2) > 1e-9:
            rel_diff_pct = (abs(val1 - val2) / abs(val2)) * 100.0
            return rel_diff_pct <= tol

        return False

    def verify_against_calculation(
        self,
        claim_num: NumericClaimValue,
        calc: CalculationEvidence,
    ) -> NumericVerificationDetail:
        """Audit claimed numerical value against a deterministic calculation receipt."""
        claimed_val = claim_num.numeric_value
        source_val = calc.calculated_value
        is_pct_metric = calc.unit.lower() == "percentage" or "%" in calc.unit

        # Case 1: Percentage vs Fraction error (e.g. 0.3013 instead of 30.13%, or 0.3013% instead of 30.13%)
        if is_pct_metric:
            if math.isclose(
                claimed_val * 100.0, source_val, rel_tol=0.05
            ) or math.isclose(claimed_val, source_val * 100.0, rel_tol=0.05):
                return NumericVerificationDetail(
                    matched=False,
                    claimed_value=claimed_val,
                    source_value=source_val,
                    claimed_unit=claim_num.unit or "%",
                    source_unit=calc.unit,
                    error_type="scale_error_percentage_vs_fraction",
                    discrepancy_details=(
                        f"Scale error: Claimed {claimed_val} appears to be a fraction mistaken for "
                        f"a percentage. Source receipt specifies {source_val}%."
                    ),
                    tolerance_pct_applied=self.tolerance_pct,
                )

        # Case 2: Sign mismatch (e.g. claim is positive, receipt is negative or vice versa)
        if (claimed_val > 0 and source_val < 0) or (claimed_val < 0 and source_val > 0):
            if self.is_close_within_tolerance(abs(claimed_val), abs(source_val)):
                return NumericVerificationDetail(
                    matched=False,
                    claimed_value=claimed_val,
                    source_value=source_val,
                    claimed_unit=claim_num.unit,
                    source_unit=calc.unit,
                    error_type="sign_mismatch",
                    discrepancy_details=(
                        f"Sign error: Claim stated {claimed_val} whereas source calculation "
                        f"receipt is {source_val}."
                    ),
                    tolerance_pct_applied=self.tolerance_pct,
                )

        # Case 3: Direct or tolerance match
        if self.is_close_within_tolerance(claimed_val, source_val):
            return NumericVerificationDetail(
                matched=True,
                claimed_value=claimed_val,
                source_value=source_val,
                claimed_unit=claim_num.unit,
                source_unit=calc.unit,
                error_type="none",
                discrepancy_details=f"Exact match with calculation receipt {calc.calculation_id}.",
                tolerance_pct_applied=self.tolerance_pct,
            )

        # Case 3.5: Match against calculation input observations (e.g. underlying components, deltas, or trend metrics)
        for obs in getattr(calc, "input_observations", []):
            obs_val = obs.get("value")
            if obs_val is not None and isinstance(obs_val, (int, float)):
                obs_unit = obs.get("unit", calc.unit)
                is_obs_pct = obs_unit.lower() == "percentage" or "%" in str(obs_unit)
                if self.is_close_within_tolerance(claimed_val, obs_val):
                    return NumericVerificationDetail(
                        matched=True,
                        claimed_value=claimed_val,
                        source_value=obs_val,
                        claimed_unit=claim_num.unit,
                        source_unit=obs_unit,
                        error_type="none",
                        discrepancy_details=(
                            f"Matched input observation '{obs.get('input_name', 'input')}' ({obs_val}) "
                            f"in calculation receipt {calc.calculation_id}."
                        ),
                        tolerance_pct_applied=self.tolerance_pct,
                    )
                if is_obs_pct and (
                    math.isclose(claimed_val * 100.0, obs_val, rel_tol=0.05)
                    or math.isclose(claimed_val, obs_val * 100.0, rel_tol=0.05)
                ):
                    return NumericVerificationDetail(
                        matched=False,
                        claimed_value=claimed_val,
                        source_value=obs_val,
                        claimed_unit=claim_num.unit or "%",
                        source_unit=obs_unit,
                        error_type="scale_error_percentage_vs_fraction",
                        discrepancy_details=(
                            f"Scale error on input '{obs.get('input_name', 'input')}': Claimed {claimed_val} "
                            f"appears to be a fraction mistaken for a percentage (source: {obs_val}%)."
                        ),
                        tolerance_pct_applied=self.tolerance_pct,
                    )

        # Case 4: Value discrepancy
        return NumericVerificationDetail(
            matched=False,
            claimed_value=claimed_val,
            source_value=source_val,
            claimed_unit=claim_num.unit,
            source_unit=calc.unit,
            error_type="value_mismatch",
            discrepancy_details=(
                f"Value mismatch: Claim stated {claimed_val} {claim_num.unit or ''}, but calculation "
                f"receipt {calc.calculation_id} computes {source_val} {calc.unit}."
            ),
            tolerance_pct_applied=self.tolerance_pct,
        )

    def extract_numbers_from_passage(self, text: str) -> list[dict[str, Any]]:
        """Extract all candidate numerical entities from a statutory text chunk."""
        # Find scale indicators in passage: e.g. "(in millions)", "(in thousands)"
        passage_scale = 1.0
        t_lower = text.lower()
        if "in millions" in t_lower or "(in millions)" in t_lower:
            passage_scale = 1e6
        elif "in thousands" in t_lower or "(in thousands)" in t_lower:
            passage_scale = 1e3
        elif "in billions" in t_lower or "(in billions)" in t_lower:
            passage_scale = 1e9

        candidates: list[dict[str, Any]] = []
        # Pattern matching numbers with optional currency and multiplier
        pattern = re.compile(
            r"(\$?\s*[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$?\s*[-+]?\d+(?:\.\d+)?)\s*"
            r"(%|(?:trillion|billion|million|thousand|percent)\b)?",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            raw_val_str = match.group(1).replace("$", "").replace(",", "").strip()
            unit_token = match.group(2).lower() if match.group(2) else None
            try:
                num = float(raw_val_str)
            except ValueError:
                continue

            scale = passage_scale
            is_pct = unit_token in {"%", "percent"} or "%" in match.group(0)
            if unit_token == "trillion":
                scale = 1e12
            elif unit_token == "billion":
                scale = 1e9
            elif unit_token == "million":
                scale = 1e6
            elif unit_token == "thousand":
                scale = 1e3

            normalized = num * scale if not is_pct else num
            candidates.append(
                {
                    "raw": match.group(0).strip(),
                    "value": num,
                    "normalized": normalized,
                    "scale": scale,
                    "is_percentage": is_pct,
                }
            )

        return candidates

    def verify_against_filing_passage(
        self,
        claim_num: NumericClaimValue,
        passage: RetrievedEvidence,
    ) -> NumericVerificationDetail:
        """Audit claimed numerical value against numbers present in a statutory filing passage."""
        passage_numbers = self.extract_numbers_from_passage(passage.chunk_text)
        if not passage_numbers:
            return NumericVerificationDetail(
                matched=False,
                claimed_value=claim_num.numeric_value,
                source_value=None,
                error_type="missing_source_value",
                discrepancy_details="No numerical figures found in referenced SEC filing passage.",
                tolerance_pct_applied=self.tolerance_pct,
            )

        claimed_norm = claim_num.normalized_value or claim_num.numeric_value

        # Check for exact normalized match
        for cand in passage_numbers:
            cand_norm = cand["normalized"]
            if self.is_close_within_tolerance(claimed_norm, cand_norm):
                return NumericVerificationDetail(
                    matched=True,
                    claimed_value=claim_num.numeric_value,
                    source_value=cand["value"],
                    claimed_unit=claim_num.unit,
                    source_unit=passage.section_identifier,
                    error_type="none",
                    discrepancy_details=f"Matched value in {passage.ticker} {passage.filing_type} passage.",
                    tolerance_pct_applied=self.tolerance_pct,
                )

        # Check for scale error: thousands vs millions error
        for cand in passage_numbers:
            # 1,000x difference check
            ratio = (
                (claimed_norm / cand["normalized"]) if cand["normalized"] != 0 else 0
            )
            if math.isclose(ratio, 1000.0, rel_tol=0.05) or math.isclose(
                ratio, 0.001, rel_tol=0.05
            ):
                return NumericVerificationDetail(
                    matched=False,
                    claimed_value=claim_num.numeric_value,
                    source_value=cand["value"],
                    claimed_unit=claim_num.unit,
                    source_unit="USD",
                    error_type="scale_error_thousands_vs_millions",
                    discrepancy_details=(
                        f"Scale error: Claimed {claim_num.raw_text} diverges by 1,000x from "
                        f"source passage figure {cand['raw']} (thousands vs millions conversion error)."
                    ),
                    tolerance_pct_applied=self.tolerance_pct,
                )

        # Check for sign mismatch
        for cand in passage_numbers:
            if math.isclose(abs(claimed_norm), abs(cand["normalized"]), rel_tol=0.05):
                if (claimed_norm > 0 and cand["normalized"] < 0) or (
                    claimed_norm < 0 and cand["normalized"] > 0
                ):
                    return NumericVerificationDetail(
                        matched=False,
                        claimed_value=claim_num.numeric_value,
                        source_value=cand["value"],
                        error_type="sign_mismatch",
                        discrepancy_details=f"Sign mismatch: Claimed {claim_num.raw_text} vs source {cand['raw']}.",
                        tolerance_pct_applied=self.tolerance_pct,
                    )

        # Closest match fallback for diagnostic reporting
        closest_cand = min(
            passage_numbers, key=lambda c: abs(c["normalized"] - claimed_norm)
        )
        return NumericVerificationDetail(
            matched=False,
            claimed_value=claim_num.numeric_value,
            source_value=closest_cand["value"],
            claimed_unit=claim_num.unit,
            error_type="value_mismatch",
            discrepancy_details=(
                f"Numerical value mismatch: Claimed {claim_num.raw_text} does not match any "
                f"corresponding figure in passage (nearest figure was {closest_cand['raw']})."
            ),
            tolerance_pct_applied=self.tolerance_pct,
        )

    def verify_claim_numbers(
        self,
        claim: ExtractedClaim,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
    ) -> list[NumericVerificationDetail]:
        """Audit all numerical values inside an extracted claim against its cited evidence."""
        if not claim.numeric_values:
            return []

        # Index available cited evidence
        calc_map = {ce.evidence_id.upper(): ce for ce in calculation_evidence}
        retrieved_map = {re.evidence_id.upper(): re for re in retrieved_evidence}

        details: list[NumericVerificationDetail] = []

        for num_entity in claim.numeric_values:
            matched_receipt = False
            # First priority: check cited calculation receipts
            for cit_id in claim.citation_ids:
                if cit_id.upper() in calc_map:
                    calc = calc_map[cit_id.upper()]
                    det = self.verify_against_calculation(num_entity, calc)
                    details.append(det)
                    matched_receipt = True
                    break

            if matched_receipt:
                continue

            # Second priority: check cited filing passages
            matched_passage = False
            for cit_id in claim.citation_ids:
                if cit_id.upper() in retrieved_map:
                    rev = retrieved_map[cit_id.upper()]
                    det = self.verify_against_filing_passage(num_entity, rev)
                    details.append(det)
                    matched_passage = True
                    break

            if not matched_passage and not matched_receipt:
                # Claim cited no evidence or cited non-existent evidence
                details.append(
                    NumericVerificationDetail(
                        matched=False,
                        claimed_value=num_entity.numeric_value,
                        claimed_unit=num_entity.unit,
                        source_value=None,
                        error_type="missing_source_value",
                        discrepancy_details=f"Number {num_entity.raw_text} has no valid supporting citation.",
                        tolerance_pct_applied=self.tolerance_pct,
                    )
                )

        return details
