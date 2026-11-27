"""Claim-to-Evidence Support Verifier for Finova AI.

Evaluates whether individual extracted assertions are genuinely supported by cited
SEC filing passages and deterministic calculation receipts. Separates citation presence
from semantic support through layered deterministic, numerical, temporal, and lexical checks.
"""

from __future__ import annotations

import re
from typing import Any

from backend.llm.llm_provider import LLMProvider
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.contradiction_detector import ContradictionDetector
from backend.verification.numeric_verifier import NumericVerifier
from backend.verification.period_verifier import PeriodVerifier
from backend.verification.verification_models import (
    ClaimVerificationResult,
    ExtractedClaim,
    VerificationOutcome,
)
from config.settings import Settings, get_settings

logger = get_logger("evidence_verifier")


class EvidenceVerifier:
    """Verifies that individual claims are grounded in and supported by cited evidence."""

    def __init__(
        self,
        numeric_verifier: NumericVerifier | None = None,
        period_verifier: PeriodVerifier | None = None,
        contradiction_detector: ContradictionDetector | None = None,
        llm_provider: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.numeric_verifier = numeric_verifier or NumericVerifier(
            settings=self.settings
        )
        self.period_verifier = period_verifier or PeriodVerifier(settings=self.settings)
        self.contradiction_detector = contradiction_detector or ContradictionDetector()
        self.llm_provider = llm_provider
        self.overlap_threshold = getattr(
            self.settings, "VERIFICATION_SEMANTIC_OVERLAP_THRESHOLD", 0.25
        )

    def _make_result(
        self,
        claim: ExtractedClaim,
        outcome: VerificationOutcome,
        verification_reason: str,
        verification_method: str,
        confidence_score: float = 1.0,
        is_verifiable: bool = True,
        supporting_evidence_ids: list[str] | None = None,
        contradicting_evidence_ids: list[str] | None = None,
        numeric_check: Any = None,
        period_check: Any = None,
        contradiction_check: Any = None,
        warnings: list[str] | None = None,
    ) -> ClaimVerificationResult:
        """Construct ClaimVerificationResult while strictly preserving extracted claim metadata."""
        return ClaimVerificationResult(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            numeric_values=claim.numeric_values,
            mentioned_company=claim.mentioned_company,
            mentioned_period=claim.mentioned_period,
            outcome=outcome,
            citation_ids=list(claim.citation_ids),
            is_verifiable=is_verifiable,
            supporting_evidence_ids=supporting_evidence_ids or [],
            contradicting_evidence_ids=contradicting_evidence_ids or [],
            verification_reason=verification_reason,
            confidence_score=confidence_score,
            verification_method=verification_method,
            numeric_check=numeric_check,
            period_check=period_check,
            contradiction_check=contradiction_check,
            warnings=warnings or [],
        )

    def compute_token_overlap(self, text1: str, text2: str) -> float:
        """Compute Jaccard token overlap between two strings, ignoring common stopwords."""
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "is",
            "was",
            "were",
            "are",
            "of",
            "by",
            "that",
            "this",
            "it",
            "as",
            "be",
            "from",
            "has",
            "had",
            "have",
            "its",
            "their",
            "reported",
            "stated",
        }
        tokens1 = {
            w.lower()
            for w in re.findall(r"\b[a-zA-Z0-9_\-\.%]+\b", text1)
            if w.lower() not in stopwords and len(w) > 1
        }
        tokens2 = {
            w.lower()
            for w in re.findall(r"\b[a-zA-Z0-9_\-\.%]+\b", text2)
            if w.lower() not in stopwords and len(w) > 1
        }
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1 & tokens2
        # Asymmetric containment: what fraction of the claim's content tokens appear in the passage?
        # Enforce content length penalty: fragments with < 3 tokens cannot claim 100% containment
        raw_containment = len(intersection) / len(tokens1)
        if len(tokens1) < 3:
            containment = raw_containment * 0.4
        else:
            containment = raw_containment

        union = tokens1 | tokens2
        jaccard = len(intersection) / len(union)
        return max(containment, jaccard)

    @staticmethod
    def detect_polarity_contradiction(claim_text: str, passage_text: str) -> tuple[bool, str]:
        """Detect directional polarity conflict between claim assertion and passage disclosure."""
        c_lower = claim_text.lower()
        p_lower = passage_text.lower()

        positive_words = {
            "increased", "increase", "grew", "growth", "rose", "expanded",
            "higher", "positive", "surpassed", "exceeded", "improvement", "gains",
        }
        negative_words = {
            "decreased", "decrease", "declined", "decline", "fell", "contracted",
            "lower", "negative", "dropped", "reduced", "loss", "losses", "slumped",
        }

        claim_has_pos = any(re.search(rf"\b{w}\b", c_lower) for w in positive_words)
        claim_has_neg = any(re.search(rf"\b{w}\b", c_lower) for w in negative_words)
        passage_has_pos = any(re.search(rf"\b{w}\b", p_lower) for w in positive_words)
        passage_has_neg = any(re.search(rf"\b{w}\b", p_lower) for w in negative_words)

        # If claim asserts increase but passage only asserts decrease
        if claim_has_pos and not claim_has_neg and passage_has_neg and not passage_has_pos:
            return True, "Claim asserts positive growth/increase, but cited passage reports decline/decrease."

        # If claim asserts decrease but passage only asserts increase
        if claim_has_neg and not claim_has_pos and passage_has_pos and not passage_has_neg:
            return True, "Claim asserts decline/decrease, but cited passage reports growth/increase."

        return False, ""

    def verify_claim(
        self,
        claim: ExtractedClaim,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
    ) -> ClaimVerificationResult:
        """Evaluate an extracted claim against available evidence items.

        Returns:
            ClaimVerificationResult with structured verdict, reasons, and checks.
        """
        # If claim is not verifiable (e.g. pleasantry, meta-conclusion)
        if not claim.is_verifiable:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.NOT_VERIFIABLE,
                is_verifiable=False,
                verification_reason="Claim is an introductory remark, greeting, or subjective meta-statement.",
                confidence_score=0.5,
                verification_method="unverifiable_filter",
            )

        # Check 1: Citation presence
        if not claim.citation_ids:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.UNSUPPORTED,
                verification_reason="Claim makes factual assertions without providing any supporting citation.",
                confidence_score=1.0,
                verification_method="citation_presence_check",
                warnings=["Claim lacks supporting citation."],
            )

        calc_map = {ce.evidence_id.upper(): ce for ce in calculation_evidence}
        retrieved_map = {re.evidence_id.upper(): re for re in retrieved_evidence}

        # Check 2: Check for fabricated citation IDs
        all_available_ids = set(calc_map.keys()) | set(retrieved_map.keys())
        cited_upper = [c.upper() for c in claim.citation_ids]
        missing_ids = [c for c in cited_upper if c not in all_available_ids]

        if missing_ids:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.UNSUPPORTED,
                contradicting_evidence_ids=[],
                verification_reason=f"Claim references non-existent or fabricated citation ID(s): {', '.join(missing_ids)}.",
                confidence_score=1.0,
                verification_method="citation_existence_check",
                warnings=[f"Fabricated citation ID(s): {', '.join(missing_ids)}"],
            )

        # Check 3: Contradiction Detection
        contra_detail = self.contradiction_detector.check_claim_contradiction(
            claim=claim,
            retrieved_evidence=retrieved_evidence,
            calculation_evidence=calculation_evidence,
        )
        if contra_detail.has_contradiction:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.CONTRADICTED,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[contra_detail.contradicting_evidence_id]
                if contra_detail.contradicting_evidence_id
                else [],
                verification_reason=f"Direct contradiction detected: {contra_detail.explanation}",
                confidence_score=1.0,
                verification_method="contradiction_detector",
                contradiction_check=contra_detail,
                warnings=[f"Contradiction: {contra_detail.explanation}"],
            )

        # Check 4: Period Consistency Verification
        period_detail = self.period_verifier.verify_claim_period(
            claim=claim,
            retrieved_evidence=retrieved_evidence,
            calculation_evidence=calculation_evidence,
        )
        if not period_detail.is_consistent:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.UNSUPPORTED,
                verification_reason=f"Reporting period inconsistency: {period_detail.explanation}",
                confidence_score=0.95,
                verification_method="period_verifier",
                period_check=period_detail,
                warnings=[period_detail.explanation],
            )

        # Check 4.5: Company Attribution Consistency Verification
        if claim.mentioned_company:
            ticker_aliases = {
                "aapl": "apple",
                "msft": "microsoft",
                "tsla": "tesla",
                "nvda": "nvidia",
                "amzn": "amazon",
                "goog": "google",
                "googl": "google",
                "meta": "meta",
            }
            claim_comp = claim.mentioned_company.lower()
            for cid in cited_upper:
                if cid in retrieved_map:
                    passage = retrieved_map[cid]
                    p_ticker = (passage.ticker or "").lower()
                    p_name = (passage.company_name or "").lower()
                    p_alias = ticker_aliases.get(p_ticker, "")
                    if p_ticker or p_name or p_alias:
                        company_match = (
                            (
                                p_ticker
                                and (claim_comp in p_ticker or p_ticker in claim_comp)
                            )
                            or (
                                p_name
                                and (claim_comp in p_name or p_name in claim_comp)
                            )
                            or (
                                p_alias
                                and (claim_comp in p_alias or p_alias in claim_comp)
                            )
                        )
                        if not company_match:
                            return self._make_result(
                                claim=claim,
                                outcome=VerificationOutcome.CONTRADICTED,
                                verification_reason=(
                                    f"Company attribution mismatch: Claim refers to '{claim.mentioned_company}' "
                                    f"but cited passage {cid} belongs to '{passage.company_name}' ({passage.ticker})."
                                ),
                                confidence_score=0.98,
                                verification_method="company_verifier",
                                warnings=[
                                    f"Company attribution mismatch: {claim.mentioned_company} vs {passage.ticker}"
                                ],
                            )

        # Check 5: Numerical Verification
        numeric_details = self.numeric_verifier.verify_claim_numbers(
            claim=claim,
            retrieved_evidence=retrieved_evidence,
            calculation_evidence=calculation_evidence,
        )
        has_num_mismatch = any(not nd.matched for nd in numeric_details)
        if has_num_mismatch:
            first_fail = next(nd for nd in numeric_details if not nd.matched)
            # Check if sign mismatch or scale error
            outcome = (
                VerificationOutcome.CONTRADICTED
                if first_fail.error_type == "sign_mismatch"
                else VerificationOutcome.UNSUPPORTED
            )
            return self._make_result(
                claim=claim,
                outcome=outcome,
                verification_reason=f"Numerical mismatch: {first_fail.discrepancy_details}",
                confidence_score=0.98,
                verification_method="numeric_verifier",
                numeric_check=first_fail,
                period_check=period_detail,
                warnings=[first_fail.discrepancy_details],
            )

        # Check 6: Deterministic Calculation Receipt Match & Semantic Trend Verification
        cited_calcs = [calc_map[cid] for cid in cited_upper if cid in calc_map]
        if cited_calcs:
            calc = cited_calcs[0]
            calc_inputs = getattr(calc, "inputs", None) or getattr(calc, "input_observations", None) or []
            is_trend = (
                "trend" in str(calc.calculation_id).lower()
                or "trend" in str(calc.metric_name).lower()
                or getattr(calc, "trajectory", None) is not None
                or len(getattr(calc, "periods", [])) > 1
                or len(getattr(calc, "observations", [])) > 1
                or (isinstance(calc_inputs, list) and any("observation_" in str(inp.get("input_name", "") if isinstance(inp, dict) else "") for inp in calc_inputs))
            )

            if is_trend:
                from backend.finance.financial_trends import verify_trend_semantics

                sem_ok, sem_outcome, sem_reason = verify_trend_semantics(
                    claim_text=claim.claim_text,
                    receipt=calc,
                    numeric_values=claim.numeric_values,
                    tolerance_pct=self.numeric_verifier.tolerance_pct,
                )
                if not sem_ok:
                    outcome = (
                        VerificationOutcome.CONTRADICTED
                        if sem_outcome == "contradicted"
                        else VerificationOutcome.UNSUPPORTED
                    )
                    contra_ids = (
                        [calc.evidence_id] if sem_outcome == "contradicted" else []
                    )
                    return self._make_result(
                        claim=claim,
                        outcome=outcome,
                        verification_reason=sem_reason,
                        verification_method="trend_semantic_verifier",
                        confidence_score=0.98 if sem_outcome == "contradicted" else 0.95,
                        contradicting_evidence_ids=contra_ids,
                        period_check=period_detail,
                        warnings=[sem_reason],
                    )

                return self._make_result(
                    claim=claim,
                    outcome=VerificationOutcome.SUPPORTED,
                    verification_reason=sem_reason,
                    verification_method="trend_semantic_verifier",
                    confidence_score=1.0,
                    supporting_evidence_ids=[calc.evidence_id],
                    period_check=period_detail,
                )
            else:
                # Single-period calculation receipt verification
                c_lower = claim.claim_text.lower()
                calc_m_clean = (
                    calc.metric_name.lower().replace("_", " ").strip()
                )

                known_metrics = {
                    "revenue": "revenue",
                    "sales": "revenue",
                    "gross profit": "gross_profit_margin",
                    "gross margin": "gross_profit_margin",
                    "operating margin": "operating_profit_margin",
                    "operating income": "operating_profit_margin",
                    "net margin": "net_profit_margin",
                    "net income": "net_profit_margin",
                    "current ratio": "current_ratio",
                    "quick ratio": "quick_ratio",
                    "debt to equity": "debt_to_equity",
                    "free cash flow": "free_cash_flow",
                    "return on assets": "return_on_assets",
                    "return on equity": "return_on_equity",
                }
                mismatch_metric = None
                for kw, canon in known_metrics.items():
                    if kw in c_lower:
                        canon_clean = canon.replace("_", " ")
                        if (
                            canon_clean not in calc_m_clean
                            and calc_m_clean not in canon_clean
                            and kw not in calc_m_clean
                        ):
                            mismatch_metric = kw
                            break
                if mismatch_metric:
                    return self._make_result(
                        claim=claim,
                        outcome=VerificationOutcome.UNSUPPORTED,
                        verification_reason=(
                            f"Metric mismatch: Claim asserts '{mismatch_metric}' which differs from cited "
                            f"calculation receipt {calc.calculation_id} ({calc.metric_name})."
                        ),
                        confidence_score=0.95,
                        verification_method="metric_alignment_check",
                        period_check=period_detail,
                        warnings=[f"Metric mismatch with receipt {calc.calculation_id}"],
                    )

                return self._make_result(
                    claim=claim,
                    outcome=VerificationOutcome.SUPPORTED,
                    verification_reason=(
                        f"Deterministic calculation receipt {calc.evidence_id} ({calc.calculation_id}) "
                        f"verifies {calc.metric_name} = {calc.calculated_value:.4f} {calc.unit}."
                    ),
                    verification_method="deterministic_receipt",
                    confidence_score=1.0,
                    supporting_evidence_ids=[calc.evidence_id],
                    period_check=period_detail,
                )

        # Check 7: Lexical & Semantic Overlap with Cited Filing Passages
        cited_passages = [
            retrieved_map[cid] for cid in cited_upper if cid in retrieved_map
        ]
        if not cited_passages:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.UNSUPPORTED,
                verification_reason="Claim has no verifiable source passages attached.",
                confidence_score=1.0,
                verification_method="citation_resolution",
            )

        # Content sufficiency check: fragments lacking substance cannot claim supported status
        clean_text_no_cites = re.sub(r"\[[^\]]+\]", "", claim.claim_text)
        claim_content_words = [
            w
            for w in re.findall(r"\b[a-zA-Z0-9_\-\.%]+\b", clean_text_no_cites)
            if len(w) > 1
            and w.lower()
            not in {
                "the",
                "a",
                "an",
                "of",
                "in",
                "to",
                "and",
                "is",
                "was",
                "for",
                "with",
                "by",
                "at",
                "from",
            }
        ]
        if len(claim_content_words) < 3 and not claim.numeric_values:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.NOT_VERIFIABLE,
                is_verifiable=False,
                verification_reason="Claim has insufficient substantive content tokens (<3) to establish verified evidence support.",
                confidence_score=0.5,
                verification_method="content_sufficiency_check",
            )

        # Evaluate token overlap across cited passages
        best_overlap = 0.0
        best_passage = cited_passages[0]
        for p in cited_passages:
            overlap = self.compute_token_overlap(claim.claim_text, p.chunk_text)
            if overlap > best_overlap:
                best_overlap = overlap
                best_passage = p

        # Directional polarity conflict check between narrative claim and cited passage
        has_polar_contra, polar_reason = self.detect_polarity_contradiction(
            claim.claim_text, best_passage.chunk_text
        )
        if has_polar_contra:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.CONTRADICTED,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[best_passage.evidence_id],
                verification_reason=f"Directional polarity contradiction: {polar_reason}",
                confidence_score=0.95,
                verification_method="polarity_contradiction_check",
                period_check=period_detail,
                warnings=[polar_reason],
            )

        # Check if passage has valid provenance status
        if getattr(best_passage, "provenance_status", "valid") not in {
            "valid",
            "whitelisted",
        }:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.PARTIALLY_SUPPORTED,
                supporting_evidence_ids=[best_passage.evidence_id],
                verification_reason=f"Passage {best_passage.evidence_id} has questionable provenance status: {best_passage.provenance_status}.",
                confidence_score=0.6,
                verification_method="provenance_audit",
                warnings=[
                    f"Questionable provenance status: {best_passage.provenance_status}"
                ],
            )

        # If claim had matched numbers and overlap is adequate
        if numeric_details and all(nd.matched for nd in numeric_details):
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.SUPPORTED,
                supporting_evidence_ids=[best_passage.evidence_id],
                verification_reason=(
                    f"Numerical figures matched and lexical overlap ({best_overlap:.1%}) confirms "
                    f"passage {best_passage.evidence_id} ({best_passage.section_identifier})."
                ),
                confidence_score=0.95,
                verification_method="deterministic_numeric_and_lexical",
                numeric_check=numeric_details[0] if numeric_details else None,
                period_check=period_detail,
            )

        # Pure qualitative / narrative assertion:
        if best_overlap >= self.overlap_threshold:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.SUPPORTED,
                supporting_evidence_ids=[best_passage.evidence_id],
                verification_reason=(
                    f"Lexical overlap ({best_overlap:.1%}) with passage {best_passage.evidence_id} "
                    f"supports narrative assertion."
                ),
                confidence_score=round(min(1.0, 0.70 + best_overlap * 0.3), 2),
                verification_method="lexical_overlap",
                period_check=period_detail,
            )
        elif best_overlap >= 0.12:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.PARTIALLY_SUPPORTED,
                supporting_evidence_ids=[best_passage.evidence_id],
                verification_reason=(
                    f"Partial lexical overlap ({best_overlap:.1%}) found in passage {best_passage.evidence_id}. "
                    "Claim is partially supported by cited disclosures."
                ),
                confidence_score=round(0.50 + best_overlap * 0.2, 2),
                verification_method="partial_lexical_overlap",
                period_check=period_detail,
                warnings=["Partial evidence overlap."],
            )
        else:
            return self._make_result(
                claim=claim,
                outcome=VerificationOutcome.UNSUPPORTED,
                supporting_evidence_ids=[],
                verification_reason=(
                    f"Insufficient evidence overlap ({best_overlap:.1%}) with cited passage {best_passage.evidence_id}. "
                    "Passage does not support the stated claim."
                ),
                confidence_score=0.85,
                verification_method="lexical_overlap",
                period_check=period_detail,
                warnings=[
                    f"Cited passage {best_passage.evidence_id} does not corroborate claim text."
                ],
            )
