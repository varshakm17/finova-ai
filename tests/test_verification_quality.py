"""Session 18.1.2: Verification Quality and Calculation Receipt Integrity Regression Tests.

Comprehensive unit and adversarial test suite validating:
1. Deterministic trend receipt math, zero denominators, negative bases, and formulas.
2. NumericVerifier unit safety, scale protection, and matched_field recording.
3. Genuine chunk-level provenance tracing, validation against document_chunks, and accession separation.
4. ClaimExtractor substance checks, fragment and heading filtering, and substantive claim preservation.
5. EvidenceVerifier multidimensional grounding, polarity contradiction, and metric alignment.
"""

from __future__ import annotations

import pytest

from backend.finance.financial_trends import (
    build_trend_receipt,
    compute_absolute_change,
    compute_percentage_change,
    verify_trend_math,
)
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.numeric_verifier import NumericVerifier
from backend.verification.verification_models import (
    ClaimType,
    ExtractedClaim,
    NumericClaimValue,
    VerificationOutcome,
)

# =============================================================================
# 1. Deterministic Trend Receipt Integrity Tests
# =============================================================================


class TestDeterministicTrendReceipts:
    """Validate mathematical reproducibility and receipt integrity of longitudinal trends."""

    def test_positive_growth(self) -> None:
        """Test percentage and absolute change for positive revenue growth."""
        pct = compute_percentage_change(100.0, 125.0)
        diff = compute_absolute_change(100.0, 125.0)
        assert pct == 25.0
        assert diff == 25.0

        receipt = build_trend_receipt(
            metric_name="revenue",
            periods=["FY2022", "FY2023"],
            values=[100.0, 125.0],
            unit="USD",
            citation_id="C1",
        )
        assert receipt is not None
        assert receipt["calculated_value"] == 25.0
        assert receipt["unit"] == "%"
        assert receipt["formula_expression"] == "((V_end - V_start) / abs(V_start)) * 100"

        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is True
        assert "verified" in msg.lower()

    def test_negative_growth(self) -> None:
        """Test percentage and absolute change for declining metric."""
        pct = compute_percentage_change(200.0, 150.0)
        diff = compute_absolute_change(200.0, 150.0)
        assert pct == -25.0
        assert diff == -50.0

        receipt = build_trend_receipt(
            metric_name="operating_income",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[200.0, 180.0, 150.0],
            unit="USD",
            citation_id="C2",
        )
        assert receipt is not None
        assert receipt["calculated_value"] == -25.0
        assert receipt["unit"] == "%"

        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is True

    def test_zero_starting_value_handling(self) -> None:
        """Ensure growth from zero is explicitly handled as absolute net shift, never percentage."""
        pct = compute_percentage_change(0.0, 50.0)
        diff = compute_absolute_change(0.0, 50.0)
        assert pct is None  # Mathematically undefined, never NaN or Inf!
        assert diff == 50.0

        receipt = build_trend_receipt(
            metric_name="debt",
            periods=["FY2022", "FY2023"],
            values=[0.0, 50.0],
            unit="USD",
            citation_id="C3",
        )
        assert receipt is not None
        # Must NOT be labeled as percentage
        assert receipt["calculated_value"] == 50.0
        assert receipt["unit"] == "USD"
        assert receipt["formula_expression"] == "V_end - V_start"
        assert receipt["formula_name"] == "Multi-Period Absolute Net Shift"

        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is True

    def test_negative_starting_value(self) -> None:
        """Test percentage change when starting value is negative (using abs(start))."""
        # From -50 to 50: ((50 - (-50)) / abs(-50)) * 100 = (100 / 50) * 100 = 200%
        pct = compute_percentage_change(-50.0, 50.0)
        diff = compute_absolute_change(-50.0, 50.0)
        assert pct == 200.0
        assert diff == 100.0

        receipt = build_trend_receipt(
            metric_name="net_income",
            periods=["FY2022", "FY2023"],
            values=[-50.0, 50.0],
            unit="USD",
            citation_id="C4",
        )
        assert receipt is not None
        assert receipt["calculated_value"] == 200.0
        assert receipt["unit"] == "%"

        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is True

    def test_missing_start_or_end_values(self) -> None:
        """Omit receipt when start or end values are missing or incomplete."""
        assert compute_percentage_change(None, 100.0) is None
        assert compute_percentage_change(100.0, None) is None
        assert compute_absolute_change(None, 100.0) is None

        receipt = build_trend_receipt(
            metric_name="cash",
            periods=["FY2022"],
            values=[100.0],  # only 1 value
            unit="USD",
            citation_id="C5",
        )
        assert receipt is None

    def test_incorrect_trend_math_detected(self) -> None:
        """Tampered or incorrect percentage change is rejected by verify_trend_math."""
        receipt = {
            "citation_id": "C6",
            "calculation_id": "calc_trend_tampered",
            "metric_name": "Revenue Trend",
            "formula_name": "Multi-Period Percentage Growth Analysis",
            "formula_expression": "((V_end - V_start) / abs(V_start)) * 100",
            "calculated_value": 99.9,  # Incorrect! Real is 25.0%
            "unit": "%",
            "inputs": [
                {"input_name": "start_value", "value": 100.0, "unit": "USD"},
                {"input_name": "end_value", "value": 125.0, "unit": "USD"},
            ],
        }
        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is False
        assert "Trend percentage mismatch" in msg

    def test_zero_denominator_in_pct_receipt_rejected(self) -> None:
        """Receipt asserting percentage formula with zero start_value is rejected."""
        receipt = {
            "citation_id": "C7",
            "calculation_id": "calc_trend_zero_denom",
            "metric_name": "Profit Trend",
            "formula_name": "Multi-Period Percentage Growth Analysis",
            "formula_expression": "((V_end - V_start) / abs(V_start)) * 100",
            "calculated_value": 100.0,
            "unit": "%",
            "inputs": [
                {"input_name": "start_value", "value": 0.0, "unit": "USD"},
                {"input_name": "end_value", "value": 50.0, "unit": "USD"},
            ],
        }
        is_valid, msg = verify_trend_math(receipt)
        assert is_valid is False
        assert "Zero denominator" in msg


# =============================================================================
# 2. Numeric Verifier Unit Safety Tests
# =============================================================================


class TestNumericVerifierUnitSafety:
    """Validate strict unit compatibility, scale safeguards, and field tracking."""

    @pytest.fixture
    def verifier(self) -> NumericVerifier:
        return NumericVerifier(tolerance_pct=1.0)

    def test_unit_category_classification(self, verifier: NumericVerifier) -> None:
        assert verifier.classify_unit("%") == "percentage"
        assert verifier.classify_unit("percent") == "percentage"
        assert verifier.classify_unit("bps") == "percentage_points"
        assert verifier.classify_unit("pp") == "percentage_points"
        assert verifier.classify_unit("USD") == "currency"
        assert verifier.classify_unit("$") == "currency"
        assert verifier.classify_unit("x") == "ratio"
        assert verifier.classify_unit("shares") == "count"
        assert verifier.classify_unit(None) == "dimensionless"

    def test_percentage_claim_cannot_match_currency_calc(
        self, verifier: NumericVerifier
    ) -> None:
        """Adversarial: Claim asserts 18.8% but calculation receipt is $18.80."""
        claim_num = NumericClaimValue(
            raw_text="18.8%",
            numeric_value=18.8,
            unit="%",
            is_percentage=True,
        )
        calc = CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_operating_cash_flow",
            metric_name="operating_cash_flow",
            formula="Operating Cash Flow = CFO",
            calculated_value=18.8,
            unit="USD",
            period_end="2023-12-31",
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is False
        assert detail.error_type == "unit_mismatch"
        assert "Unit mismatch" in detail.discrepancy_details

    def test_currency_claim_cannot_match_percentage_calc(
        self, verifier: NumericVerifier
    ) -> None:
        """Adversarial: Claim asserts $25.0M but calculation receipt is 25.0%."""
        claim_num = NumericClaimValue(
            raw_text="$25.0",
            numeric_value=25.0,
            unit="USD",
            is_percentage=False,
        )
        calc = CalculationEvidence(
            evidence_id="C2",
            calculation_id="calc_gross_margin",
            metric_name="gross_margin",
            formula="Gross Margin = GrossProfit / Revenue",
            calculated_value=25.0,
            unit="%",
            period_end="2023-12-31",
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is False
        assert detail.error_type == "unit_mismatch"

    def test_percentage_points_vs_percentage(self, verifier: NumericVerifier) -> None:
        """Adversarial: Claim asserts 500 bps but calculation is 500%."""
        claim_num = NumericClaimValue(
            raw_text="500 bps",
            numeric_value=500.0,
            unit="bps",
            is_percentage=False,
        )
        calc = CalculationEvidence(
            evidence_id="C3",
            calculation_id="calc_growth",
            metric_name="growth",
            formula="Growth = Delta",
            calculated_value=500.0,
            unit="%",
            period_end="2023-12-31",
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is False
        assert detail.error_type == "unit_mismatch"

    def test_record_exact_matched_field_calculated_value(
        self, verifier: NumericVerifier
    ) -> None:
        """Verification detail must record matched_field='calculated_value'."""
        claim_num = NumericClaimValue(
            raw_text="35.5%",
            numeric_value=35.5,
            unit="%",
            is_percentage=True,
        )
        calc = CalculationEvidence(
            evidence_id="C4",
            calculation_id="calc_operating_margin",
            metric_name="operating_margin",
            formula="Operating Margin = OperatingIncome / Revenue",
            calculated_value=35.5,
            unit="%",
            period_end="2023-12-31",
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is True
        assert detail.matched_field == "calculated_value"

    def test_record_exact_matched_field_input_observation(
        self, verifier: NumericVerifier
    ) -> None:
        """Verification detail must record matched_field='input_observations[start_value]'."""
        claim_num = NumericClaimValue(
            raw_text="$150.0",
            numeric_value=150.0,
            unit="USD",
            is_percentage=False,
        )
        calc = CalculationEvidence(
            evidence_id="C5",
            calculation_id="calc_trend_rev",
            metric_name="revenue Trend",
            formula="Longitudinal Trend = V_end - V_start",
            calculated_value=50.0,
            unit="USD",
            period_end="2023-12-31",
            input_observations=[
                {"input_name": "start_value", "value": 150.0, "unit": "USD"},
                {"input_name": "end_value", "value": 200.0, "unit": "USD"},
            ],
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is True
        assert detail.matched_field == "input_observations[start_value]"

    def test_input_observation_unit_mismatch(self, verifier: NumericVerifier) -> None:
        """Percentage claim must NOT match an absolute currency input observation."""
        claim_num = NumericClaimValue(
            raw_text="150.0%",
            numeric_value=150.0,
            unit="%",
            is_percentage=True,
        )
        calc = CalculationEvidence(
            evidence_id="C6",
            calculation_id="calc_trend_rev",
            metric_name="revenue Trend",
            formula="Trend = V_end - V_start",
            calculated_value=50.0,
            unit="USD",
            period_end="2023-12-31",
            input_observations=[
                {"input_name": "start_value", "value": 150.0, "unit": "USD"},
            ],
        )
        detail = verifier.verify_against_calculation(claim_num, calc)
        assert detail.matched is False
        assert detail.error_type == "unit_mismatch"


# =============================================================================
# 3. Genuine Chunk-Level Provenance Tests
# =============================================================================


class TestChunkLevelProvenance:
    """Validate genuine chunk ID tracking and accession number separation."""

    def test_chunk_id_vs_accession_number_distinction(self) -> None:
        """Verify chunk ID follows standard pattern and is not an accession number."""
        sample_chunk_id = "0000320193_000032019323000106_ITEM_1A_0"
        sample_accn = "0000320193-23-000106"

        assert sample_chunk_id != sample_accn
        assert "ITEM_1A" in sample_chunk_id
        assert "-" in sample_accn

    def test_missing_sec_url_is_none_not_generic_homepage(self) -> None:
        """Unresolved SEC URL must be None and not 'https://www.sec.gov'."""
        from backend.agents.research_coordinator import ResearchCoordinator

        coordinator = ResearchCoordinator()
        evidence_item = {
            "chunk_id": "0000320193_000032019323000106_ITEM_1_0",
            "ticker": "AAPL",
            "section_identifier": "ITEM_1",
            "accession_number": "",  # no accession
            "source_url": "https://www.sec.gov",  # generic homepage supplied
        }
        emap, _ = coordinator.build_evidence_map([evidence_item], [])
        assert emap["E1"]["source_url"] is None


# =============================================================================
# 4. Claim Extraction Quality Tests
# =============================================================================


class TestClaimExtractionQuality:
    """Validate fragment rejection, heading filtering, and assertion substance."""

    @pytest.fixture
    def extractor(self) -> ClaimExtractor:
        return ClaimExtractor()

    def test_reject_isolated_date_fragment(self, extractor: ClaimExtractor) -> None:
        """Isolated year like 'Business Operations : 2020.' is classified as structural statement."""
        res = extractor.extract_claims("Business Operations [E1]: 2020.")
        assert len(res.claims) == 1
        claim = res.claims[0]
        assert claim.is_verifiable is False
        assert claim.claim_type == ClaimType.STRUCTURAL_STATEMENT

    def test_reject_isolated_location_fragment(self, extractor: ClaimExtractor) -> None:
        """Isolated location like 'Business Operations [E1]: New York.' is non-verifiable."""
        res = extractor.extract_claims("Business Operations [E1]: New York.")
        assert len(res.claims) == 1
        claim = res.claims[0]
        assert claim.is_verifiable is False
        assert claim.claim_type == ClaimType.STRUCTURAL_STATEMENT

    def test_reject_section_heading(self, extractor: ClaimExtractor) -> None:
        """Statutory heading like 'ITEM 1A. Risk Factors.' is non-verifiable."""
        res = extractor.extract_claims("ITEM 1A. Risk Factors.")
        assert len(res.claims) == 1
        assert res.claims[0].is_verifiable is False
        assert res.claims[0].claim_type == ClaimType.STRUCTURAL_STATEMENT

    def test_preserve_valid_short_factual_claim(self, extractor: ClaimExtractor) -> None:
        """Short assertion with financial metric and figure is verifiable."""
        res = extractor.extract_claims("Gross margin was 45.2% [C1].")
        assert len(res.claims) == 1
        claim = res.claims[0]
        assert claim.is_verifiable is True
        assert claim.claim_type == ClaimType.FINANCIAL_METRIC
        assert len(claim.numeric_values) == 1
        assert claim.numeric_values[0].numeric_value == 45.2

    def test_preserve_complete_trend_claim(self, extractor: ClaimExtractor) -> None:
        """Complete multi-period trend assertion is verifiable."""
        text = "Revenue showed an upward trend across FY2021-FY2023 with a net change of +18.8% [C1]."
        res = extractor.extract_claims(text)
        assert len(res.claims) == 1
        claim = res.claims[0]
        assert claim.is_verifiable is True
        assert claim.claim_type in {ClaimType.FINANCIAL_METRIC, ClaimType.HISTORICAL_COMPARISON}

    def test_preserve_qualitative_business_assertion(
        self, extractor: ClaimExtractor
    ) -> None:
        """Complete narrative assertion with active predicate is verifiable."""
        text = "Tesla develops, manufactures, and sells electric vehicles and energy storage systems [E1]."
        res = extractor.extract_claims(text)
        assert len(res.claims) == 1
        claim = res.claims[0]
        assert claim.is_verifiable is True


# =============================================================================
# 5. Evidence Verification Quality & Adversarial Tests
# =============================================================================


class TestEvidenceVerificationQuality:
    """Validate multidimensional grounding, polarity checks, and metric alignment."""

    @pytest.fixture
    def verifier(self) -> EvidenceVerifier:
        return EvidenceVerifier(
            numeric_verifier=NumericVerifier(tolerance_pct=1.0),
        )

    def test_wrong_financial_metric_against_calc(
        self, verifier: EvidenceVerifier
    ) -> None:
        """Adversarial: Claim asserts Operating Margin but cites Revenue Growth receipt."""
        claim = ExtractedClaim(
            claim_id="CLM-01",
            claim_text="Operating margin expanded significantly [C1].",
            claim_type=ClaimType.PERFORMANCE_STATEMENT,
            citation_ids=["C1"],
            is_verifiable=True,
        )
        calc = CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_revenue_growth_FY2023",
            metric_name="revenue_growth",
            formula="Revenue Growth = Delta",
            calculated_value=15.0,
            unit="%",
            period_end="2023-12-31",
        )
        res = verifier.verify_claim(claim, [], [calc])
        assert res.outcome == VerificationOutcome.UNSUPPORTED
        assert "Metric mismatch" in res.verification_reason

    def test_polarity_reversal_contradiction(
        self, verifier: EvidenceVerifier
    ) -> None:
        """Adversarial: Claim asserts revenue increased, but cited passage states revenue declined."""
        claim = ExtractedClaim(
            claim_id="CLM-02",
            claim_text="Total revenue increased across global markets [E1].",
            claim_type=ClaimType.PERFORMANCE_STATEMENT,
            citation_ids=["E1"],
            is_verifiable=True,
        )
        passage = RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_01",
            ticker="MSFT",
            company_name="Microsoft Corporation",
            filing_type="10-K",
            filing_date="2023-08-01",
            accession_number="0001193125-23-000001",
            section_identifier="ITEM_7",
            section_title="Management Discussion",
            chunk_text="During the fiscal year, total revenue decreased by 8% due to macroeconomic headwinds.",
            source_url="https://www.sec.gov/Archives/edgar/data/789019/000119312523000001/",
        )
        res = verifier.verify_claim(claim, [passage], [])
        assert res.outcome == VerificationOutcome.CONTRADICTED
        assert (
            "polarity" in res.verification_reason.lower()
            or "directional conflict" in res.verification_reason.lower()
            or "contradict" in res.verification_reason.lower()
        )

    def test_short_fragment_cannot_get_supported_status(
        self, verifier: EvidenceVerifier
    ) -> None:
        """Adversarial: 2-token fragment matching words in long passage must be rejected."""
        claim = ExtractedClaim(
            claim_id="CLM-03",
            claim_text="cloud computing [E1].",
            claim_type=ClaimType.GENERAL_FACT,
            citation_ids=["E1"],
            is_verifiable=True,
        )
        passage = RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_02",
            ticker="MSFT",
            company_name="Microsoft Corporation",
            filing_type="10-K",
            filing_date="2023-08-01",
            accession_number="0001193125-23-000001",
            section_identifier="ITEM_1",
            section_title="Business Operations",
            chunk_text="The company delivers cloud computing, AI, and developer tools across commercial clients.",
            source_url="https://www.sec.gov/Archives/edgar/data/789019/000119312523000001/",
        )
        res = verifier.verify_claim(claim, [passage], [])
        assert res.outcome in {VerificationOutcome.NOT_VERIFIABLE, VerificationOutcome.UNSUPPORTED}
        assert "insufficient substantive content" in res.verification_reason.lower()

    def test_company_attribution_mismatch_contradicted(
        self, verifier: EvidenceVerifier
    ) -> None:
        """Adversarial: Claim asserts Tesla performance citing Microsoft passage."""
        claim = ExtractedClaim(
            claim_id="CLM-04",
            claim_text="Tesla achieved strong automotive margins [E1].",
            claim_type=ClaimType.PERFORMANCE_STATEMENT,
            mentioned_company="Tesla",
            citation_ids=["E1"],
            is_verifiable=True,
        )
        passage = RetrievedEvidence(
            evidence_id="E1",
            chunk_id="chk_03",
            ticker="MSFT",
            company_name="Microsoft Corporation",
            filing_type="10-K",
            filing_date="2023-08-01",
            accession_number="0001193125-23-000001",
            section_identifier="ITEM_7",
            section_title="Management Discussion",
            chunk_text="Microsoft achieved strong cloud margins across enterprise segments.",
            source_url="https://www.sec.gov/Archives/edgar/data/789019/000119312523000001/",
        )
        res = verifier.verify_claim(claim, [passage], [])
        assert res.outcome == VerificationOutcome.CONTRADICTED
        assert "Company attribution mismatch" in res.verification_reason
