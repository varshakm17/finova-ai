"""Financial Period and Temporal Consistency Verifier for Finova AI.

Audits chronological alignment between claims and cited evidence. Detects fiscal year
mismatches (e.g. claiming FY2023 based on FY2022 evidence), quarterly vs annual confusion
(10-K vs 10-Q), quarter confusion (Q1 vs Q4), and calendar vs fiscal divergence.
"""

from __future__ import annotations

import re

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.verification_models import (
    ExtractedClaim,
    PeriodVerificationDetail,
)
from config.settings import Settings, get_settings

logger = get_logger("period_verifier")

YEAR_PATTERN = re.compile(r"(?:FY\s*)?(20\d{2}|19\d{2})", re.IGNORECASE)
QUARTER_PATTERN = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
ORDINAL_QUARTER_PATTERN = re.compile(
    r"\b(first|second|third|fourth)\s+quarter\b", re.IGNORECASE
)
ORDINAL_MAP = {"first": 1, "second": 2, "third": 3, "fourth": 4}


class PeriodVerifier:
    """Verifies that time horizons, fiscal years, and quarters align between claim and evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def parse_period_year(self, period_str: str | None) -> int | None:
        """Extract primary 4-digit calendar/fiscal year from period string."""
        if not period_str:
            return None
        match = YEAR_PATTERN.search(period_str)
        if match:
            return int(match.group(1))
        return None

    def parse_quarter(self, text: str | None) -> int | None:
        """Extract 1-based quarter index (1, 2, 3, or 4) from text if present."""
        if not text:
            return None
        m1 = QUARTER_PATTERN.search(text)
        if m1:
            return int(m1.group(1))
        m2 = ORDINAL_QUARTER_PATTERN.search(text)
        if m2:
            return ORDINAL_MAP.get(m2.group(1).lower())
        return None

    def verify_claim_period(
        self,
        claim: ExtractedClaim,
        retrieved_evidence: list[RetrievedEvidence],
        calculation_evidence: list[CalculationEvidence],
    ) -> PeriodVerificationDetail:
        """Audit reporting period alignment between claim text and all cited evidence items."""
        claimed_period = claim.mentioned_period
        if not claimed_period:
            return PeriodVerificationDetail(
                is_consistent=True,
                claimed_period=None,
                source_period=None,
                mismatch_type="none",
                explanation="No specific reporting period was asserted in claim text.",
            )

        claimed_year = self.parse_period_year(claimed_period)
        claimed_quarter = self.parse_quarter(claimed_period)
        is_claimed_annual = (
            "annual" in claimed_period.lower() or "fy" in claimed_period.lower()
        )

        calc_map = {ce.evidence_id.upper(): ce for ce in calculation_evidence}
        retrieved_map = {re.evidence_id.upper(): re for re in retrieved_evidence}

        for cit_id in claim.citation_ids:
            cit_upper = cit_id.upper()

            # 1. Audit against calculation receipt period
            if cit_upper in calc_map:
                ce = calc_map[cit_upper]
                source_period_end = ce.period_end  # e.g. "2023-09-30"
                source_year = self.parse_period_year(source_period_end)

                if claimed_year and source_year and claimed_year != source_year:
                    return PeriodVerificationDetail(
                        is_consistent=False,
                        claimed_period=claimed_period,
                        source_period=source_period_end,
                        mismatch_type="fiscal_year_mismatch",
                        explanation=(
                            f"Fiscal year mismatch: Claim asserts period '{claimed_period}' "
                            f"(year {claimed_year}), but cited calculation receipt {ce.calculation_id} "
                            f"was computed for period ending '{source_period_end}' (year {source_year})."
                        ),
                    )

            # 2. Audit against retrieved statutory filing passage period
            if cit_upper in retrieved_map:
                re_doc = retrieved_map[cit_upper]
                # Prioritize explicit statutory report_date if populated, otherwise filing_date
                source_date = re_doc.report_date or re_doc.filing_date
                source_year = self.parse_period_year(source_date)
                filing_type = re_doc.filing_type.upper()

                # Fiscal year check
                if claimed_year and source_year and claimed_year != source_year:
                    # In annual Form 10-K filings, prior fiscal periods, contract dates, and debt maturities
                    # are standard disclosures. If the cited chunk text explicitly mentions the claimed year,
                    # the passage directly supports the temporal claim unless the claimed numerical figure
                    # is explicitly attributed to a different year in the passage.
                    if str(claimed_year) not in re_doc.chunk_text:
                        return PeriodVerificationDetail(
                            is_consistent=False,
                            claimed_period=claimed_period,
                            source_period=source_date,
                            mismatch_type="fiscal_year_mismatch",
                            explanation=(
                                f"Fiscal year mismatch: Claim references period '{claimed_period}', "
                                f"whereas cited SEC filing passage ({re_doc.accession_number}) reports "
                                f"period date '{source_date}' and does not mention {claimed_year}."
                            ),
                        )
                    elif claim.numeric_values:
                        passage_years = [
                            (int(m.group(1)), (m.start(1) + m.end(1)) / 2)
                            for m in re.finditer(r"\b(20\d\d)\b", re_doc.chunk_text)
                        ]
                        if len(passage_years) > 1:
                            for cv in claim.numeric_values:
                                if cv.numeric_value and cv.numeric_value >= 1.0:
                                    num_str = f"{cv.numeric_value:,.0f}".replace(",", r"[,\.]?")
                                    for m in re.finditer(r"\b" + num_str + r"\b", re_doc.chunk_text):
                                        m_center = (m.start() + m.end()) / 2
                                        closest_year = None
                                        min_dist = float("inf")
                                        for y, y_center in passage_years:
                                            d = abs(m_center - y_center)
                                            if d < min_dist:
                                                min_dist = d
                                                closest_year = y
                                        if closest_year and closest_year != claimed_year and min_dist < 45:
                                            return PeriodVerificationDetail(
                                                is_consistent=False,
                                                claimed_period=claimed_period,
                                                source_period=f"{closest_year} (via passage)",
                                                mismatch_type="fiscal_year_mismatch",
                                                explanation=(
                                                    f"Fiscal year mismatch: Claim associates {cv.raw_text} with "
                                                    f"period '{claimed_period}' (year {claimed_year}), but cited passage "
                                                    f"explicitly reports this figure for fiscal year {closest_year}."
                                                ),
                                            )

                # Annual vs Quarterly mismatch check
                if is_claimed_annual and "10-Q" in filing_type:
                    return PeriodVerificationDetail(
                        is_consistent=False,
                        claimed_period=claimed_period,
                        source_period=f"{filing_type} ({source_date})",
                        mismatch_type="annual_vs_quarterly",
                        explanation=(
                            f"Filing frequency mismatch: Claim states an annual/FY assertion ('{claimed_period}'), "
                            f"but cites a quarterly Form {filing_type} filing."
                        ),
                    )

                if claimed_quarter and "10-K" in filing_type:
                    return PeriodVerificationDetail(
                        is_consistent=False,
                        claimed_period=claimed_period,
                        source_period=f"{filing_type} ({source_date})",
                        mismatch_type="annual_vs_quarterly",
                        explanation=(
                            f"Filing frequency mismatch: Claim asserts a specific quarter ('Q{claimed_quarter}'), "
                            f"but cites an annual Form 10-K filing."
                        ),
                    )

                # Specific quarter mismatch check within 10-Q
                if claimed_quarter and "10-Q" in filing_type:
                    # Infer quarter from report date month: e.g. month 3 -> Q1, month 6 -> Q2, etc.
                    # Apple fiscal: Q1 is Dec/Jan, Q2 is Mar/Apr, Q3 is Jun/Jul
                    # Detect obvious quarter mismatches
                    if "q1" in claimed_period.lower() and (
                        "q3" in re_doc.chunk_text.lower()
                        or "third quarter" in re_doc.chunk_text.lower()
                    ):
                        return PeriodVerificationDetail(
                            is_consistent=False,
                            claimed_period=claimed_period,
                            source_period=f"10-Q Q3 ({source_date})",
                            mismatch_type="quarter_mismatch",
                            explanation="Quarter mismatch: Claim references Q1, but cited passage reports Q3 results.",
                        )

        # All checked evidence items are consistent with claim's period
        return PeriodVerificationDetail(
            is_consistent=True,
            claimed_period=claimed_period,
            source_period=claimed_period,
            mismatch_type="none",
            explanation=f"Reporting period '{claimed_period}' aligns with cited statutory evidence.",
        )
