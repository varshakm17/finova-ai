"""Adversarial tests for observation-to-period alignment and provenance metadata integrity.

Covers 15 required scenarios:
1. Valid three-year observations with matching period labels pass.
2. Observation period differs from the corresponding periods-array entry.
3. Observation labels are shifted by one fiscal year.
4. Observation objects are out of chronological order.
5. Duplicate observation period labels.
6. Missing observation period.
7. Missing intermediate annual period.
8. period_start disagrees with the first observation.
9. period_end disagrees with the last observation.
10. Numeric-only observations with an independently supplied valid period sequence remain supported.
11. Historical calculation ID and fiscal-year metadata conflict.
12. Calculation period dates conflict with fiscal-year metadata.
13. A provenance record references an accession that cannot be established.
14. An observation-period mismatch propagates to the claim's reconciled outcome.
15. A provenance failure prevents the company from receiving a fully verified status.
"""


from backend.finance.financial_trends import (
    TrendReceiptAuditor,
    validate_calculation_provenance,
    verify_trend_math,
)
from backend.rag.rag_models import CalculationEvidence
from backend.verification.claim_extractor import ExtractedClaim
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.verification_models import (
    ClaimType,
    NumericClaimValue,
    VerificationOutcome,
)


def test_scenario_01_valid_three_year_observations_pass():
    """1. Valid three-year observations with matching period labels pass."""
    receipt = {
        "calculation_id": "calc_trend_revenue_growth_FY2021_FY2023",
        "metric_name": "revenue_growth Trend",
        "formula_name": "Multi-Period Percentage Growth Analysis",
        "formula_expression": "((V_end - V_start) / abs(V_start)) * 100",
        "calculated_value": 100.0,
        "unit": "%",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "percentage_change": 100.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "%"},
            {"period": "FY2022", "value": 15.0, "unit": "%"},
            {"period": "FY2023", "value": 20.0, "unit": "%"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "%"},
            {"input_name": "end_value", "value": 20.0, "unit": "%"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "%"},
            {"input_name": "percentage_change", "value": 100.0, "unit": "%"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is True, f"Expected valid, got: {msg}"
    assert "verified" in msg.lower()


def test_scenario_02_observation_period_differs_from_periods_array():
    """2. Observation period differs from the corresponding periods-array entry."""
    receipt = {
        "calculation_id": "calc_trend_rev_01",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2024"],  # Discrepancy at index 2
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "Observation period mismatch at index 2" in msg


def test_scenario_03_observation_labels_shifted_by_one_fiscal_year():
    """3. Observation labels are shifted by one fiscal year."""
    receipt = {
        "calculation_id": "calc_trend_rev_02",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2020", "value": 10.0, "unit": "USD"},  # Shifted back 1 year
            {"period": "FY2021", "value": 15.0, "unit": "USD"},
            {"period": "FY2022", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "Observation period mismatch at index 0" in msg


def test_scenario_04_observation_objects_out_of_chronological_order():
    """4. Observation objects are out of chronological order."""
    receipt = {
        "calculation_id": "calc_trend_rev_03",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2022", "FY2021", "FY2023"],  # Out of order
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "out of chronological order" in msg.lower()


def test_scenario_05_duplicate_observation_period_labels():
    """5. Duplicate observation period labels."""
    receipt = {
        "calculation_id": "calc_trend_rev_04",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2022",
        "periods": ["FY2021", "FY2022", "FY2022"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2022", "value": 20.0, "unit": "USD"},  # Duplicate
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "duplicate observation period labels" in msg.lower()


def test_scenario_06_missing_observation_period():
    """6. Missing observation period."""
    receipt = {
        "calculation_id": "calc_trend_rev_05",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": None, "value": 15.0, "unit": "USD"},  # Missing period
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "missing observation period in observation object at index 1" in msg.lower()


def test_scenario_07_missing_intermediate_annual_period():
    """7. Missing intermediate annual period."""
    receipt = {
        "calculation_id": "calc_trend_rev_06",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2023"],  # Skips FY2022
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "missing intermediate annual period" in msg.lower()


def test_scenario_08_period_start_disagrees_with_first_observation():
    """8. period_start disagrees with the first observation."""
    receipt = {
        "calculation_id": "calc_trend_rev_07",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2020",  # Disagrees with FY2021
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "period_start mismatch" in msg.lower()


def test_scenario_09_period_end_disagrees_with_last_observation():
    """9. period_end disagrees with the last observation."""
    receipt = {
        "calculation_id": "calc_trend_rev_08",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2024",  # Disagrees with FY2023
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is False
    assert "period_end mismatch" in msg.lower()


def test_scenario_10_numeric_only_observations_with_valid_periods_pass():
    """10. Numeric-only observations with an independently supplied valid period sequence remain supported."""
    receipt = {
        "calculation_id": "calc_trend_rev_09",
        "metric_name": "revenue Trend",
        "formula_name": "Multi-Period Absolute Net Shift",
        "formula_expression": "V_end - V_start",
        "calculated_value": 10.0,
        "unit": "USD",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "values": [10.0, 15.0, 20.0],  # Numeric-only
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    }
    valid, msg = verify_trend_math(receipt)
    assert valid is True, f"Expected numeric-only observations to pass, got: {msg}"
    assert "verified" in msg.lower()


def test_scenario_11_calculation_id_and_fiscal_year_metadata_conflict():
    """11. Historical calculation ID and fiscal-year metadata conflict."""
    calc = {
        "calculation_id": "0000789019_revenue_growth_annual_2021-06-30",
        "metric_name": "revenue_growth",
        "fiscal_year": 2023,  # Conflicts with 2021 encoded in calculation_id
        "period_end": "2023-06-30",  # Matches fiscal_year 2023 so calculation_id conflict triggers
        "calculated_value": 17.53,
        "unit": "%",
        "status": "calculated",
        "input_observations": [
            {
                "metric_name": "Revenues",
                "value": 168088000000.0,
                "accession_number": "0000789019-21-000056",
                "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000078901921000056/msft-20210630.htm",
            }
        ],
    }
    valid, msg, details = validate_calculation_provenance(calc)
    assert valid is False
    assert "Provenance conflict" in msg
    assert "encodes year 2021 which conflicts with stored fiscal_year 2023" in msg


def test_scenario_12_calculation_period_dates_conflict_with_fiscal_year():
    """12. Calculation period dates conflict with fiscal-year metadata."""
    calc = {
        "calculation_id": "calc_msft_rev_growth_2021",
        "metric_name": "revenue_growth",
        "fiscal_year": 2024,  # Conflicts with period_end 2021-06-30
        "period_end": "2021-06-30",
        "calculated_value": 17.53,
        "unit": "%",
        "status": "calculated",
        "input_observations": [
            {
                "metric_name": "Revenues",
                "value": 168088000000.0,
                "accession_number": "0000789019-21-000056",
                "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000078901921000056/msft-20210630.htm",
            }
        ],
    }
    valid, msg, details = validate_calculation_provenance(calc)
    assert valid is False
    assert "Provenance conflict" in msg
    assert "conflicts with stored fiscal_year 2024" in msg


def test_scenario_13_provenance_record_unestablished_accession():
    """13. A provenance record references an accession that cannot be established."""
    calc = {
        "calculation_id": "0000789019_revenue_growth_annual_2023-06-30",
        "metric_name": "revenue_growth",
        "fiscal_year": 2023,
        "period_end": "2023-06-30",
        "calculated_value": 6.88,
        "unit": "%",
        "status": "calculated",
        "input_observations": [
            {
                "metric_name": "Revenues",
                "value": 211915000000.0,
                "accession_number": "INVALID-ACCESSION-NUMBER",  # Fails SEC accession pattern
                "source_url": "https://www.sec.gov/Archives/edgar/data/789019/msft-20230630.htm",
            }
        ],
    }
    valid, msg, details = validate_calculation_provenance(calc)
    assert valid is False
    assert "Unestablished or malformed SEC accession number" in msg


def test_scenario_14_observation_period_mismatch_propagates_to_claim_outcome():
    """14. An observation-period mismatch propagates to the claim's reconciled outcome."""
    verifier = EvidenceVerifier()
    claim = ExtractedClaim(
        claim_id="clm_trend_01",
        claim_text="Revenue demonstrated steady growth across the period. [C1]",
        claim_type=ClaimType.HISTORICAL_COMPARISON,
        is_verifiable=True,
        citation_ids=["C1"],
        numeric_values=[
            NumericClaimValue(raw_text="10.0", numeric_value=10.0, unit="USD"),
            NumericClaimValue(raw_text="20.0", numeric_value=20.0, unit="USD"),
        ],
    )

    bad_receipt = CalculationEvidence(
        evidence_id="C1",
        calculation_id="calc_trend_rev_mismatch",
        metric_name="revenue Trend",
        calculated_value=10.0,
        unit="USD",
        formula="V_end - V_start",
        period_start="FY2021",
        period_end="FY2023",
        periods=["FY2021", "FY2022", "FY2024"],  # Mismatch with observations
        direction="UPWARD",
        trajectory="MONOTONIC_UPWARD",
        observations=[
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        input_observations=[
            {"period": "FY2021", "value": 10.0, "unit": "USD"},
            {"period": "FY2022", "value": 15.0, "unit": "USD"},
            {"period": "FY2023", "value": 20.0, "unit": "USD"},
        ],
        inputs=[
            {"input_name": "start_value", "value": 10.0, "unit": "USD"},
            {"input_name": "end_value", "value": 20.0, "unit": "USD"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "USD"},
        ],
    )

    cvr = verifier.verify_claim(claim, [], [bad_receipt])
    assert cvr.outcome == VerificationOutcome.UNSUPPORTED
    assert "Observation period mismatch at index 2" in cvr.verification_reason


def test_scenario_15_provenance_failure_prevents_verified_status():
    """15. A provenance failure prevents the company from receiving a fully verified status."""
    auditor = TrendReceiptAuditor()
    # Trend receipt with unestablished SEC accession in provenance
    bad_receipt = {
        "calculation_id": "0000789019_revenue_growth_annual_trend_2023",
        "metric_name": "revenue_growth Trend",
        "formula_name": "Multi-Period Percentage Growth Analysis",
        "formula_expression": "((V_end - V_start) / abs(V_start)) * 100",
        "calculated_value": 100.0,
        "unit": "%",
        "start_value": 10.0,
        "end_value": 20.0,
        "absolute_change": 10.0,
        "percentage_change": 100.0,
        "period_start": "FY2021",
        "period_end": "FY2023",
        "fiscal_year": 2023,
        "periods": ["FY2021", "FY2022", "FY2023"],
        "trajectory": "MONOTONIC_UPWARD",
        "observations": [
            {"period": "FY2021", "value": 10.0, "unit": "%"},
            {"period": "FY2022", "value": 15.0, "unit": "%"},
            {"period": "FY2023", "value": 20.0, "unit": "%"},
        ],
        "inputs": [
            {"input_name": "start_value", "value": 10.0, "unit": "%"},
            {"input_name": "end_value", "value": 20.0, "unit": "%"},
            {"input_name": "absolute_change", "value": 10.0, "unit": "%"},
            {"input_name": "percentage_change", "value": 100.0, "unit": "%"},
        ],
        "input_observations": [
            {
                "metric_name": "Revenues",
                "value": 1000000.0,
                "accession_number": "MALFORMED_ACCESSION",  # Invalid
                "source_url": "https://www.sec.gov/Archives/edgar/data/789019/test.htm",
            }
        ],
    }

    audit_res = auditor.audit_receipt(bad_receipt, citation_id="C1")
    assert audit_res["is_valid"] is False
    assert audit_res["provenance_valid"] is False
    assert audit_res["status"] == "failed_provenance"
    assert "Unestablished or malformed SEC accession number" in audit_res["verification_reason"]
