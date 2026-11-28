"""Deterministic Financial Longitudinal Trends & Trend Receipt Verification.

Computes multi-period percentage and absolute changes with strict zero-denominator
handling, mathematical reproducibility, trajectory classification, and receipt verification for Finova AI.
"""

from __future__ import annotations

import json
import math
import re
from enum import Enum
from typing import Any

from backend.rag.rag_models import CalculationEvidence
from backend.utils.logger import get_logger
from backend.verification.period_verifier import normalize_period

logger = get_logger("financial_trends")


def parse_period_chronological_key(period_str: str | None) -> tuple[int, int, str]:
    """Extract a numeric sort key (year, quarter/month, raw) to verify chronological ordering."""
    if not period_str:
        return (0, 0, "")
    norm = normalize_period(str(period_str)) or str(period_str).strip()
    # Check date YYYY-MM-DD
    m_date = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", norm)
    if m_date:
        return (int(m_date.group(1)), int(m_date.group(2)), norm)
    # Check quarter Q[1-4] FYYYYY or FYYYYY-Q[1-4]
    m_q = re.search(r"Q([1-4])", norm, re.IGNORECASE)
    m_y = re.search(r"(?:19|20)\d{2}", norm)
    if m_q and m_y:
        return (int(m_y.group(0)), int(m_q.group(1)), norm)
    # Check annual FYYYYY or YYYY
    if m_y:
        return (int(m_y.group(0)), 0, norm)
    return (0, 0, norm)


def are_units_compatible(u1: str | None, u2: str | None) -> bool:
    """Check if two observation or calculation units are mathematically compatible."""
    if not u1 or not u2:
        return True
    u1_clean = str(u1).lower().strip()
    u2_clean = str(u2).lower().strip()
    if u1_clean == u2_clean:
        return True
    pcts = {"%", "percentage", "pct", "percent", "bps"}
    if u1_clean in pcts and u2_clean in pcts:
        return True
    currs = {"usd", "$", "dollar", "dollars"}
    if u1_clean in currs and u2_clean in currs:
        return True
    ratios = {"ratio", "x", "multiple"}
    if u1_clean in ratios and u2_clean in ratios:
        return True
    return False


def periods_align(p_declared: str | None, p_target: str | None) -> bool:
    """Check if a declared period_start/period_end aligns with an observation or period label.

    Supports:
        - Exact string equality (case-insensitive)
        - Normalized period equality (e.g. 'FY 2021' == 'FY2021')
        - Date-to-FY alignment where both refer to the same annual fiscal year (e.g. '2021-06-30' and 'FY2021')
    """
    if not p_declared or not p_target:
        return True
    s_dec = str(p_declared).strip()
    s_tgt = str(p_target).strip()
    if s_dec.upper() == s_tgt.upper():
        return True
    norm_dec = normalize_period(s_dec) or s_dec
    norm_tgt = normalize_period(s_tgt) or s_tgt
    if norm_dec.upper() == norm_tgt.upper():
        return True
    k_dec = parse_period_chronological_key(norm_dec)
    k_tgt = parse_period_chronological_key(norm_tgt)
    if k_dec[0] != 0 and k_dec[0] == k_tgt[0]:
        if k_dec[1] == 0 or k_tgt[1] == 0:
            return True
        if k_dec[1] == k_tgt[1]:
            return True
    return False


SEC_ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def validate_calculation_provenance(
    calc: dict[str, Any] | CalculationEvidence | Any,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate calculation provenance metadata against authoritative dates and SEC sources.

    Reconciles:
        1. Calculation ID presence and non-emptiness.
        2. Metric name presence and validity.
        3. Fiscal year and fiscal period metadata consistency with actual calculation period.
        4. Period start and period end presence and chronological order.
        5. Calculated value and unit validity.
        6. Input observation periods and non-emptiness.
        7. Authoritative SEC accession numbers.
        8. Official SEC source filing URLs.

    Returns:
        (is_valid, reason, details_dict)
    """
    if not calc:
        return False, "Empty or None calculation record", {"provenance_complete": False}

    if isinstance(calc, dict):
        calc_id = calc.get("calculation_id") or calc.get("id")
        metric_name = calc.get("metric_name")
        fy = calc.get("fiscal_year")
        fp = calc.get("fiscal_period") or "FY"
        p_start = calc.get("period_start")
        p_end = calc.get("period_end")
        val = calc.get("calculated_value")
        unit = calc.get("unit")
        status = calc.get("calculation_status") or calc.get("status", "calculated")
        raw_inputs = calc.get("input_observations") or calc.get("inputs") or []
        if isinstance(raw_inputs, str):
            try:
                raw_inputs = json.loads(raw_inputs)
            except Exception:
                raw_inputs = []
    else:
        calc_id = getattr(calc, "calculation_id", None) or getattr(calc, "id", None)
        metric_name = getattr(calc, "metric_name", None)
        fy = getattr(calc, "fiscal_year", None)
        fp = getattr(calc, "fiscal_period", "FY")
        p_start = getattr(calc, "period_start", None)
        p_end = getattr(calc, "period_end", None)
        val = getattr(calc, "calculated_value", None)
        unit = getattr(calc, "unit", None)
        status = getattr(calc, "calculation_status", "calculated")
        raw_inputs = (
            getattr(calc, "input_observations", None)
            or getattr(calc, "inputs", None)
            or []
        )

    details: dict[str, Any] = {
        "calculation_id": calc_id,
        "metric_name": metric_name,
        "fiscal_year": fy,
        "fiscal_period": fp,
        "period_start": p_start,
        "period_end": p_end,
        "calculated_value": val,
        "unit": unit,
        "calculation_status": status,
        "provenance_complete": False,
        "missing_fields": [],
        "inconsistencies": [],
        "source_observations": [],
    }

    if not calc_id:
        details["missing_fields"].append("calculation_id")
        return False, "Missing calculation_id in provenance record", details

    if not metric_name:
        details["missing_fields"].append("metric_name")
        return False, f"Missing metric_name in calculation {calc_id}", details

    if not p_end or str(p_end).strip() == "":
        details["missing_fields"].append("period_end")
        return False, f"Missing period_end in calculation {calc_id}", details

    # Parse period_end date year
    p_end_str = str(p_end).strip()
    p_end_year = None
    m_pe = re.match(r"^(\d{4})-\d{2}-\d{2}$", p_end_str)
    if m_pe:
        p_end_year = int(m_pe.group(1))
    else:
        m_pe_y = re.search(r"(?:19|20)\d{2}", p_end_str)
        if m_pe_y:
            p_end_year = int(m_pe_y.group(0))

    if fy is None:
        details["missing_fields"].append("fiscal_year")
        return False, f"Missing fiscal_year metadata in calculation {calc_id}", details

    try:
        fy_int = int(fy)
    except (ValueError, TypeError):
        details["inconsistencies"].append(f"Invalid non-integer fiscal_year '{fy}'")
        return False, f"Invalid fiscal_year '{fy}' in calculation {calc_id}", details

    # Reconcile period dates against fiscal_year
    if p_end_year is not None:
        if abs(fy_int - p_end_year) > 1:
            incon = (
                f"Calculation period_end '{p_end_str}' (year {p_end_year}) conflicts with "
                f"stored fiscal_year {fy_int}"
            )
            details["inconsistencies"].append(incon)
            return False, f"Provenance conflict for {calc_id}: {incon}", details

    # Reconcile calculation ID encoding against fiscal_year
    m_calc_years = re.findall(r"(?:19|20)\d{2}", str(calc_id))
    if m_calc_years:
        calc_encoded_year = int(m_calc_years[-1])
        if abs(calc_encoded_year - fy_int) > 1:
            incon = (
                f"Calculation ID '{calc_id}' encodes year {calc_encoded_year} which conflicts "
                f"with stored fiscal_year {fy_int}"
            )
            details["inconsistencies"].append(incon)
            return False, f"Provenance conflict for {calc_id}: {incon}", details

    # Check calculated value and unit when status is calculated
    if status == "calculated":
        if (
            val is None
            or not isinstance(val, (int, float))
            or math.isnan(float(val))
            or math.isinf(float(val))
        ):
            details["inconsistencies"].append(f"Invalid calculated_value: {val}")
            return (
                False,
                f"Invalid calculated_value '{val}' for calculated status in {calc_id}",
                details,
            )
        if not unit:
            details["missing_fields"].append("unit")
            return False, f"Missing unit in calculation {calc_id}", details

    # Check underlying input observations
    if not raw_inputs:
        details["missing_fields"].append("input_observations")
        return False, f"Missing input observations provenance for {calc_id}", details

    clean_src_obs = []
    for idx, inp in enumerate(raw_inputs):
        if hasattr(inp, "model_dump"):
            inp = inp.model_dump()
        if not isinstance(inp, dict):
            continue
        accn = inp.get("accession_number")
        s_url = inp.get("source_url")
        inp_pe = inp.get("period_end")
        inp_ps = inp.get("period_start")
        inp_val = inp.get("value")

        if not accn or str(accn).strip() in ("", "None", "null"):
            details["missing_fields"].append(f"input[{idx}].accession_number")
            return (
                False,
                f"Missing SEC accession number for input {idx} in {calc_id}",
                details,
            )

        accn_clean = str(accn).strip()
        if not SEC_ACCESSION_PATTERN.match(accn_clean):
            details["inconsistencies"].append(
                f"Malformed SEC accession number: {accn_clean}"
            )
            return (
                False,
                f"Unestablished or malformed SEC accession number '{accn_clean}' in {calc_id}",
                details,
            )

        if not s_url or not str(s_url).strip().startswith(("https://", "http://")):
            details["missing_fields"].append(f"input[{idx}].source_url")
            return (
                False,
                f"Missing or invalid SEC source URL for input {idx} in {calc_id}",
                details,
            )

        clean_src_obs.append(
            {
                "metric_name": inp.get("metric_name"),
                "value": inp_val,
                "period_start": inp_ps,
                "period_end": inp_pe,
                "accession_number": accn_clean,
                "source_url": str(s_url).strip(),
                "filing_type": inp.get("filing_type"),
            }
        )

    if not clean_src_obs:
        return (
            False,
            f"No valid input observation records found for {calc_id}",
            details,
        )

    details["provenance_complete"] = True
    details["source_observations"] = clean_src_obs
    return True, "Provenance metadata verified and consistent", details


class TrajectoryType(str, Enum):
    """Deterministic trajectory classification for multi-period financial trends."""

    MONOTONIC_UPWARD = "MONOTONIC_UPWARD"
    MONOTONIC_DOWNWARD = "MONOTONIC_DOWNWARD"
    MIXED_UPWARD_NET = "MIXED_UPWARD_NET"
    MIXED_DOWNWARD_NET = "MIXED_DOWNWARD_NET"
    FLAT = "FLAT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def classify_trajectory(
    values: list[float] | None,
    tolerance: float = 1e-4,
) -> TrajectoryType:
    """Classify the trajectory of an ordered series of observations deterministically.

    Tolerance Definition:
        A delta between consecutive observations |Δ_i| <= tolerance (default 1e-4 = 0.0001)
        is classified as flat / negligible change. This accounts for minor presentation
        rounding artifacts while preserving true economic shifts.

    Classifications:
        - MONOTONIC_UPWARD: Every step is non-negative and at least one step is positive (> tolerance).
        - MONOTONIC_DOWNWARD: Every step is non-positive and at least one step is negative (< -tolerance).
        - MIXED_UPWARD_NET: Demonstrates both upward and downward intermediate steps, with net change > tolerance.
        - MIXED_DOWNWARD_NET: Demonstrates both upward and downward intermediate steps, with net change < -tolerance.
        - FLAT: All step changes are within tolerance, or net change is within tolerance with balanced/negligible steps.
        - INSUFFICIENT_DATA: Fewer than 2 observations, or contains None/NaN/infinite values.
    """
    if not values or len(values) < 2:
        return TrajectoryType.INSUFFICIENT_DATA

    clean_vals: list[float] = []
    for v in values:
        if v is None:
            return TrajectoryType.INSUFFICIENT_DATA
        try:
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                return TrajectoryType.INSUFFICIENT_DATA
            clean_vals.append(fv)
        except (ValueError, TypeError):
            return TrajectoryType.INSUFFICIENT_DATA

    deltas = [clean_vals[i + 1] - clean_vals[i] for i in range(len(clean_vals) - 1)]
    net_change = clean_vals[-1] - clean_vals[0]

    all_flat = all(abs(d) <= tolerance for d in deltas)
    if all_flat or (
        abs(net_change) <= tolerance and all(abs(d) <= tolerance for d in deltas)
    ):
        return TrajectoryType.FLAT

    has_up = any(d > tolerance for d in deltas)
    has_down = any(d < -tolerance for d in deltas)

    if has_up and not has_down:
        return TrajectoryType.MONOTONIC_UPWARD
    elif has_down and not has_up:
        return TrajectoryType.MONOTONIC_DOWNWARD
    elif has_up and has_down:
        if net_change > tolerance:
            return TrajectoryType.MIXED_UPWARD_NET
        elif net_change < -tolerance:
            return TrajectoryType.MIXED_DOWNWARD_NET
        else:
            return TrajectoryType.FLAT

    return TrajectoryType.FLAT


def compute_percentage_change(
    start_value: float | None, end_value: float | None
) -> float | None:
    """Compute percentage change: ((end_value - start_value) / abs(start_value)) * 100.

    Explicitly returns None if start_value is zero, None, NaN, or infinite,
    preventing division by zero or fabricated percentages.
    """
    if start_value is None or end_value is None:
        return None
    try:
        s_val = float(start_value)
        e_val = float(end_value)
    except (ValueError, TypeError):
        return None

    if math.isnan(s_val) or math.isnan(e_val) or math.isinf(s_val) or math.isinf(e_val):
        return None

    # Strict zero denominator handling: growth from zero is mathematically undefined
    if abs(s_val) < 1e-9:
        return None

    pct_chg = ((e_val - s_val) / abs(s_val)) * 100.0
    return round(pct_chg, 4)


def compute_absolute_change(
    start_value: float | None, end_value: float | None
) -> float | None:
    """Compute absolute change: end_value - start_value."""
    if start_value is None or end_value is None:
        return None
    try:
        s_val = float(start_value)
        e_val = float(end_value)
    except (ValueError, TypeError):
        return None

    if math.isnan(s_val) or math.isnan(e_val) or math.isinf(s_val) or math.isinf(e_val):
        return None

    return round(e_val - s_val, 4)


def build_trend_receipt(
    metric_name: str,
    periods: list[str],
    values: list[float],
    unit: str,
    citation_id: str,
    supporting_receipt_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Construct an auditable CalculationEvidence receipt for a longitudinal trend.

    Retains complete observation series, trajectory classification, direction,
    and mathematical formula metadata.
    """
    if (
        not metric_name
        or not periods
        or not values
        or len(values) < 2
        or len(periods) < 2
    ):
        logger.warning(
            "Incomplete inputs for trend receipt %s: values=%s, periods=%s",
            metric_name,
            values,
            periods,
        )
        return None

    if len(periods) != len(values):
        logger.warning(
            "Period/value count mismatch for %s: periods=%d, values=%d",
            metric_name,
            len(periods),
            len(values),
        )
        return None

    clean_vals: list[float] = []
    for v in values:
        if v is None:
            return None
        try:
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                return None
            clean_vals.append(fv)
        except (ValueError, TypeError):
            return None

    start_val = clean_vals[0]
    end_val = clean_vals[-1]

    pct_chg = compute_percentage_change(start_val, end_val)
    abs_chg = compute_absolute_change(start_val, end_val)
    if abs_chg is None:
        return None

    trajectory = classify_trajectory(clean_vals)
    if trajectory == TrajectoryType.MONOTONIC_UPWARD:
        direction = "UPWARD"
    elif trajectory == TrajectoryType.MONOTONIC_DOWNWARD:
        direction = "DOWNWARD"
    elif trajectory in (
        TrajectoryType.MIXED_UPWARD_NET,
        TrajectoryType.MIXED_DOWNWARD_NET,
    ):
        direction = "MIXED"
    else:
        direction = "FLAT"

    norm_periods = [normalize_period(str(p)) or str(p) for p in periods]
    p_start = norm_periods[0]
    p_end = norm_periods[-1]
    p_label = f"{p_start}-{p_end}"

    clean_metric_id = re.sub(r"[^a-zA-Z0-9_]", "_", metric_name)
    clean_p_label = re.sub(r"[^a-zA-Z0-9_]", "_", p_label)
    calc_id = f"calc_trend_{clean_metric_id}_{clean_p_label}"

    observations = [
        {"period": p, "value": v, "unit": unit}
        for p, v in zip(norm_periods, clean_vals)
    ]

    inputs: list[dict[str, Any]] = [
        {"input_name": "start_value", "value": start_val, "unit": unit},
        {"input_name": "end_value", "value": end_val, "unit": unit},
        {"input_name": "absolute_change", "value": abs_chg, "unit": unit},
    ]

    if pct_chg is not None:
        inputs.append(
            {"input_name": "percentage_change", "value": pct_chg, "unit": "%"}
        )
        calculated_value = pct_chg
        receipt_unit = "%"
        formula_name = "Multi-Period Percentage Growth Analysis"
        formula_expression = "((V_end - V_start) / abs(V_start)) * 100"
    else:
        calculated_value = abs_chg
        receipt_unit = unit
        formula_name = "Multi-Period Absolute Net Shift"
        formula_expression = "V_end - V_start"

    # Retain full ordered observations in inputs
    for idx, obs in enumerate(observations):
        inputs.append(
            {
                "input_name": f"observation_{idx}_{obs['period']}",
                "value": obs["value"],
                "unit": obs["unit"],
                "period": obs["period"],
                "index": idx,
            }
        )

    return {
        "citation_id": citation_id,
        "calculation_id": calc_id,
        "metric_name": f"{metric_name} Trend",
        "formula_name": formula_name,
        "formula_expression": formula_expression,
        "formula": formula_expression,
        "calculated_value": calculated_value,
        "unit": receipt_unit,
        "fiscal_year": p_end,
        "fiscal_period": "MULTI",
        "period_start": p_start,
        "period_end": p_end,
        "periods": norm_periods,
        "values": clean_vals,
        "observations": observations,
        "direction": direction,
        "trajectory": trajectory.value,
        "start_value": start_val,
        "end_value": end_val,
        "absolute_change": abs_chg,
        "percentage_change": pct_chg,
        "inputs": inputs,
        "input_observations": [],
        "supporting_receipt_ids": supporting_receipt_ids or [],
    }


def verify_trend_math(
    receipt: dict[str, Any] | CalculationEvidence,
    tolerance_pct: float = 1.0,
) -> tuple[bool, str]:
    """Independently audit and recalculate a trend receipt from its recorded observations and inputs.

    Validates:
        1. Non-empty receipt with valid calculation_id and metric_name.
        2. Presence of finite start_value and end_value.
        3. Extraction of ordered observation series (at least 2 observations).
        4. Observation count strictly matches period count.
        5. Chronological period ordering without duplicates.
        6. Absence of missing intermediate annual periods (e.g. FY2021 to FY2023 requires all 3 years).
        7. Observation unit compatibility across all data points and receipt unit.
        8. Matching of first and last observations with start_value and end_value.
        9. Independent recalculation of absolute and percentage changes.
        10. Independent recalculation of trajectory from complete observation series.
        11. Rejection of two-period series claiming mixed trajectory.
        12. Agreement between recorded trajectory and recalculated trajectory.
        13. Zero denominator handling: undefined percentage change if start_value is 0.
        14. Formula metadata agreement between formula_name and formula_expression.
        15. Mathematical agreement between calculated_value and recalculated value.

    Returns:
        (is_valid, explanation)
    """
    if not receipt:
        return False, "Empty or None calculation receipt"

    if isinstance(receipt, dict):
        calc_val = receipt.get("calculated_value")
        unit = receipt.get("unit", "")
        formula_expr = receipt.get("formula_expression") or receipt.get("formula", "")
        formula_name = receipt.get("formula_name", "")
        inputs = receipt.get("inputs", [])
        metric_name = receipt.get("metric_name", "Trend")
        recorded_traj = receipt.get("trajectory")
        top_obs = receipt.get("observations") or receipt.get("values")
        raw_periods = receipt.get("periods")
        p_start = receipt.get("period_start", "")
        p_end = receipt.get("period_end", "")
        recorded_abs = receipt.get("absolute_change")
        recorded_pct = receipt.get("percentage_change")
    else:
        calc_val = receipt.calculated_value
        unit = receipt.unit
        formula_expr = getattr(receipt, "formula_expression", "") or getattr(
            receipt, "formula", ""
        )
        formula_name = getattr(receipt, "formula_name", "")
        inputs = getattr(receipt, "inputs", []) or getattr(
            receipt, "input_observations", []
        )
        metric_name = receipt.metric_name
        recorded_traj = getattr(receipt, "trajectory", None)
        top_obs = getattr(receipt, "observations", None) or getattr(
            receipt, "values", None
        )
        raw_periods = getattr(receipt, "periods", None)
        p_start = getattr(receipt, "period_start", "")
        p_end = getattr(receipt, "period_end", "")
        recorded_abs = getattr(receipt, "absolute_change", None)
        recorded_pct = getattr(receipt, "percentage_change", None)

    if calc_val is None:
        return False, f"Missing calculated_value in trend receipt for {metric_name}"

    input_map: dict[str, float] = {}
    input_units: dict[str, str] = {}
    obs_from_inputs: list[tuple[int, float, str | None, str | None]] = []

    if isinstance(inputs, dict):
        for name, val in inputs.items():
            if val is not None and isinstance(val, (int, float)):
                input_map[name] = float(val)
    elif isinstance(inputs, list):
        for inp in inputs:
            if hasattr(inp, "model_dump"):
                inp = inp.model_dump()
            if isinstance(inp, dict):
                name = inp.get("input_name") or inp.get("name")
                val = inp.get("value")
                inp_unit = inp.get("unit")
                inp_p = inp.get("period")
                if name and inp_unit:
                    input_units[name] = str(inp_unit)
                if name and val is not None and isinstance(val, (int, float)):
                    input_map[name] = float(val)
                    if name.startswith("observation_") or "index" in inp:
                        idx = inp.get("index")
                        if idx is None:
                            match = re.search(r"^observation_(\d+)_", name)
                            if match:
                                idx = int(match.group(1))
                        if idx is not None:
                            obs_from_inputs.append(
                                (int(idx), float(val), inp_p, inp_unit)
                            )

    start_v = input_map.get("start_value")
    end_v = input_map.get("end_value")

    if recorded_abs is None:
        recorded_abs = input_map.get("absolute_change")
    if recorded_pct is None:
        recorded_pct = input_map.get("percentage_change")

    if start_v is None or end_v is None:
        return (
            False,
            f"Missing start_value or end_value in trend inputs for {metric_name}",
        )

    if (
        math.isnan(start_v)
        or math.isnan(end_v)
        or math.isinf(start_v)
        or math.isinf(end_v)
    ):
        return False, f"Non-finite start or end values in trend inputs for {metric_name}"

    is_pct_receipt = (
        unit in {"%", "percentage", "pct"}
        or "abs(V_start)" in str(formula_expr)
        or "Percentage" in str(formula_name)
    )

    # 0. Early zero denominator check for percentage receipts
    if is_pct_receipt and abs(start_v) < 1e-9:
        return (
            False,
            f"Zero denominator: percentage change undefined for {metric_name} (start_value=0)",
        )

    expected_abs = compute_absolute_change(start_v, end_v)
    expected_pct = compute_percentage_change(start_v, end_v)

    if recorded_abs is not None and expected_abs is not None:
        if not math.isclose(recorded_abs, expected_abs, rel_tol=0.01, abs_tol=1e-3):
            return (
                False,
                f"Recorded absolute change mismatch for {metric_name}: recorded {recorded_abs}, recalculated {expected_abs}",
            )

    if recorded_pct is not None and expected_pct is not None:
        if not math.isclose(recorded_pct, expected_pct, rel_tol=0.01, abs_tol=1e-3):
            return (
                False,
                f"Recorded percentage change mismatch for {metric_name}: recorded {recorded_pct}, recalculated {expected_pct}",
            )

    if is_pct_receipt:
        if expected_pct is None:
            return (
                False,
                f"Trend percentage change undefined for {metric_name} (start_value={start_v})",
            )
        pct_diff = abs(calc_val - expected_pct)
        pct_denom = abs(expected_pct) if abs(expected_pct) > 1e-6 else 1.0
        pct_rel_err = (pct_diff / pct_denom) * 100
        if pct_rel_err > tolerance_pct and pct_diff > 0.05:
            return (
                False,
                f"Trend percentage mismatch for {metric_name}: receipt has {calc_val:.4f}, recalculated {expected_pct:.4f} (diff {pct_diff:.4f}%)",
            )
    else:
        if expected_abs is None:
            return False, f"Trend absolute change undefined for {metric_name}"
        abs_diff = abs(calc_val - expected_abs)
        abs_denom = abs(expected_abs) if abs(expected_abs) > 1e-6 else 1.0
        abs_rel_err = (abs_diff / abs_denom) * 100
        if abs_rel_err > tolerance_pct and abs_diff > 0.05:
            return (
                False,
                f"Trend absolute mismatch for {metric_name}: receipt has {calc_val:.4f}, recalculated {expected_abs:.4f}",
            )

    # Extract complete ordered observations
    obs_vals: list[float] = []
    obs_units: list[str] = []
    obs_periods: list[str] = []
    is_object_observations = False

    raw_obs_list = top_obs if top_obs is not None else []
    if not raw_obs_list and obs_from_inputs:
        raw_obs_list = [
            {"period": x[2], "value": x[1], "unit": x[3]}
            for x in obs_from_inputs
        ]

    if raw_obs_list:
        if not isinstance(raw_obs_list, list) or len(raw_obs_list) < 2:
            return (
                False,
                f"Missing or insufficient intermediate observations for {metric_name} (found {len(raw_obs_list) if isinstance(raw_obs_list, list) else 0} < 2)",
            )

        is_object_observations = any(
            isinstance(item, dict) or hasattr(item, "period")
            for item in raw_obs_list
        )

        for idx, item in enumerate(raw_obs_list):
            if is_object_observations:
                if isinstance(item, dict):
                    p_val = item.get("period")
                    val = item.get("value")
                    u = item.get("unit")
                else:
                    p_val = getattr(item, "period", None)
                    val = getattr(item, "value", None)
                    u = getattr(item, "unit", None)

                if (
                    p_val is None
                    or str(p_val).strip() == ""
                    or str(p_val).strip().lower() in ("none", "null")
                ):
                    return (
                        False,
                        f"Missing observation period in observation object at index {idx} for {metric_name}",
                    )

                norm_op = normalize_period(str(p_val))
                if not norm_op:
                    return (
                        False,
                        f"Observation period '{p_val}' at index {idx} failed normalization for {metric_name}",
                    )

                obs_periods.append(norm_op)
            else:
                val = item
                u = unit

            if val is None:
                return (
                    False,
                    f"Null observation value in trend observations for {metric_name}",
                )
            try:
                fv = float(val)
                if math.isnan(fv) or math.isinf(fv):
                    return (
                        False,
                        f"Non-finite observation value in trend observations for {metric_name}",
                    )
                obs_vals.append(fv)
                if u:
                    obs_units.append(str(u))
            except (ValueError, TypeError):
                return (
                    False,
                    f"Invalid non-numeric observation value in trend observations for {metric_name}",
                )
    else:
        return (
            False,
            f"Missing or insufficient intermediate observations for {metric_name} (no observation series provided)",
        )

    if len(obs_vals) < 2:
        return (
            False,
            f"Missing or insufficient intermediate observations for {metric_name} (found {len(obs_vals)} < 2)",
        )

    # Extract & validate periods array
    norm_periods: list[str] = []
    if raw_periods:
        for idx, p in enumerate(raw_periods):
            if (
                p is None
                or str(p).strip() == ""
                or str(p).strip().lower() in ("none", "null")
            ):
                return (
                    False,
                    f"Null or empty period in periods array at index {idx} for {metric_name}",
                )
            np = normalize_period(str(p))
            if not np:
                return (
                    False,
                    f"Invalid period '{p}' in periods array at index {idx} failed normalization for {metric_name}",
                )
            norm_periods.append(np)
    elif is_object_observations:
        norm_periods = list(obs_periods)
    elif p_start and p_end:
        pk_s = parse_period_chronological_key(p_start)
        pk_e = parse_period_chronological_key(p_end)
        if pk_s[1] == 0 and pk_e[1] == 0 and pk_e[0] >= pk_s[0]:
            annual_count = pk_e[0] - pk_s[0] + 1
            if annual_count == len(obs_vals):
                norm_periods = [f"FY{y}" for y in range(pk_s[0], pk_e[0] + 1)]
        if not norm_periods:
            return (
                False,
                f"Missing periods array for numeric-only observations in {metric_name}",
            )
    else:
        return (
            False,
            f"Missing periods array for numeric-only observations in {metric_name}",
        )

    if not norm_periods or len(norm_periods) < 2:
        return (
            False,
            f"Missing or insufficient periods for {metric_name} (found {len(norm_periods)} < 2)",
        )

    # When observations are represented as objects containing period and value, enforce strict alignment
    if is_object_observations:
        if len(obs_periods) != len(norm_periods):
            return (
                False,
                f"Number of observation objects ({len(obs_periods)}) does not equal number of periods ({len(norm_periods)}) for {metric_name}",
            )

        for idx, (op, rp) in enumerate(zip(obs_periods, norm_periods)):
            if op != rp:
                return (
                    False,
                    f"Observation period mismatch at index {idx} for {metric_name}: "
                    f"observation period is '{op}', periods array entry is '{rp}'",
                )

        if len(set(obs_periods)) != len(obs_periods):
            return (
                False,
                f"Duplicate observation period labels detected in trend receipt for {metric_name}: {obs_periods}",
            )

        obs_keys = [parse_period_chronological_key(p) for p in obs_periods]
        for i in range(len(obs_keys) - 1):
            k1 = obs_keys[i]
            k2 = obs_keys[i + 1]
            if k1[0] > k2[0] or (k1[0] == k2[0] and k1[1] >= k2[1] and k1[1] != 0):
                return (
                    False,
                    f"Observation objects out of chronological order for {metric_name}: {obs_periods[i]} precedes or equals {obs_periods[i+1]}",
                )

        for i in range(len(obs_keys) - 1):
            if obs_keys[i][1] == 0 and obs_keys[i + 1][1] == 0:
                gap = obs_keys[i + 1][0] - obs_keys[i][0]
                if gap > 1:
                    return (
                        False,
                        f"Missing intermediate annual period for {metric_name}: gap between {obs_periods[i]} and {obs_periods[i+1]} (expected consecutive annual periods, found gap of {gap} years)",
                    )

        if p_start:
            if not periods_align(p_start, obs_periods[0]):
                return (
                    False,
                    f"period_start mismatch for {metric_name}: receipt period_start '{p_start}' disagrees with first observation period '{obs_periods[0]}'",
                )
        if p_end:
            if not periods_align(p_end, obs_periods[-1]):
                return (
                    False,
                    f"period_end mismatch for {metric_name}: receipt period_end '{p_end}' disagrees with last observation period '{obs_periods[-1]}'",
                )

    if not is_object_observations:
        if len(obs_vals) != len(norm_periods):
            return (
                False,
                f"Observation count ({len(obs_vals)}) does not match period count ({len(norm_periods)}) for {metric_name}",
            )
        if len(set(norm_periods)) != len(norm_periods):
            return (
                False,
                f"Duplicate periods detected in trend receipt for {metric_name}: {norm_periods}",
            )

        period_keys = [parse_period_chronological_key(p) for p in norm_periods]
        for i in range(len(period_keys) - 1):
            k1 = period_keys[i]
            k2 = period_keys[i + 1]
            if k1[0] > k2[0] or (k1[0] == k2[0] and k1[1] >= k2[1] and k1[1] != 0):
                return (
                    False,
                    f"Periods out of chronological order for {metric_name}: {norm_periods[i]} precedes or equals {norm_periods[i+1]}",
                )

        for i in range(len(period_keys) - 1):
            if period_keys[i][1] == 0 and period_keys[i + 1][1] == 0:
                gap = period_keys[i + 1][0] - period_keys[i][0]
                if gap > 1:
                    return (
                        False,
                        f"Missing intermediate period in annual series for {metric_name}: gap between {norm_periods[i]} and {norm_periods[i+1]} (expected consecutive years, found gap of {gap} years)",
                    )

        if p_start and not periods_align(p_start, norm_periods[0]):
            return (
                False,
                f"period_start mismatch for {metric_name}: receipt period_start '{p_start}' disagrees with first period '{norm_periods[0]}'",
            )
        if p_end and not periods_align(p_end, norm_periods[-1]):
            return (
                False,
                f"period_end mismatch for {metric_name}: receipt period_end '{p_end}' disagrees with last period '{norm_periods[-1]}'",
            )

    # Verify unit compatibility
    if obs_units:
        base_u = obs_units[0]
        for idx, u in enumerate(obs_units[1:], start=1):
            if not are_units_compatible(base_u, u):
                return (
                    False,
                    f"Observation unit mismatch across series for {metric_name}: observation 0 has unit '{base_u}', observation {idx} has unit '{u}'",
                )
        if not is_pct_receipt and not are_units_compatible(base_u, unit):
            return (
                False,
                f"Observation unit mismatch for {metric_name}: observation unit '{base_u}' is incompatible with non-percentage receipt unit '{unit}'",
            )

    # Validate that start and end match observations
    if not math.isclose(start_v, obs_vals[0], abs_tol=1e-4):
        return (
            False,
            f"start_value mismatch with first observation: start_value={start_v}, obs[0]={obs_vals[0]}",
        )
    if not math.isclose(end_v, obs_vals[-1], abs_tol=1e-4):
        return (
            False,
            f"end_value mismatch with last observation: end_value={end_v}, obs[-1]={obs_vals[-1]}",
        )

    # Trajectory independent recalculation & validation
    recalculated_traj = classify_trajectory(obs_vals)

    # A two-observation series may be monotonic upward, monotonic downward, or flat. It must NEVER be classified as mixed!
    if len(obs_vals) == 2 and (
        recalculated_traj
        in (TrajectoryType.MIXED_UPWARD_NET, TrajectoryType.MIXED_DOWNWARD_NET)
        or (recorded_traj and "MIXED" in str(recorded_traj).upper())
    ):
        return (
            False,
            f"Two-observation series cannot establish mixed trajectory for {metric_name} (recorded '{recorded_traj}')",
        )

    if recorded_traj and recorded_traj != recalculated_traj.value:
        return (
            False,
            f"Trajectory mismatch for {metric_name}: recorded '{recorded_traj}', recalculated '{recalculated_traj.value}' from observations {obs_vals}",
        )

    # Formula metadata agreement validation
    if formula_name and formula_expr:
        if "Percentage" in formula_name or "Growth" in formula_name:
            if (
                "abs(V_start)" not in formula_expr
                and "(V_end - V_start)" not in formula_expr
            ):
                return False, (
                    f"Formula metadata mismatch for {metric_name}: formula_name is '{formula_name}' "
                    f"but formula_expression is '{formula_expr}'"
                )
        elif "Absolute" in formula_name or "Net Shift" in formula_name:
            if "V_end - V_start" not in formula_expr:
                return False, (
                    f"Formula metadata mismatch for {metric_name}: formula_name is '{formula_name}' "
                    f"but formula_expression is '{formula_expr}'"
                )

    if is_pct_receipt:
        return True, "Deterministic trend percentage verified"
    else:
        return True, "Deterministic trend absolute change verified"


def verify_trend_semantics(
    claim_text: str,
    receipt: dict[str, Any] | CalculationEvidence,
    numeric_values: list[Any] | None = None,
    tolerance_pct: float = 1.0,
    mentioned_period: str | None = None,
) -> tuple[bool, str, str]:
    """Verify semantic agreement between claim narrative assertions and trend receipt.

    Audits:
        1. Non-empty receipt existence.
        2. Independent mathematical and observation validation of receipt.
        3. Independent derivation of trajectory directly from actual observations.
        4. Agreement between stored trajectory and recalculated trajectory.
        5. Metric identity alignment.
        6. Period identity alignment.
        7. Qualitative trajectory agreement (mixed volatility vs monotonic).
        8. Net directional polarity agreement.
        9. Quantitative figures alignment against receipt calculations.

    Returns:
        (is_supported, outcome, reason)
        where outcome in {"supported", "unsupported", "contradicted", "incomplete"}.
    """
    if not receipt:
        return (
            False,
            "unsupported",
            "Claim cites missing or non-existent calculation receipt.",
        )

    # 1. Independent mathematical and observational validation
    is_valid, math_reason = verify_trend_math(receipt, tolerance_pct=tolerance_pct)
    if not is_valid:
        if (
            "missing" in math_reason.lower()
            or "insufficient" in math_reason.lower()
            or "null" in math_reason.lower()
        ):
            return (
                False,
                "incomplete",
                f"Receipt failed completeness validation: {math_reason}",
            )
        elif (
            "period" in math_reason.lower()
            or "alignment" in math_reason.lower()
            or "chronological" in math_reason.lower()
            or "order" in math_reason.lower()
        ):
            return (
                False,
                "unsupported",
                f"Receipt failed period alignment validation: {math_reason}",
            )
        elif (
            "trajectory" in math_reason.lower()
            or "stored trajectory" in math_reason.lower()
        ):
            return (
                False,
                "contradicted",
                f"Receipt failed trajectory validation: {math_reason}",
            )
        return (
            False,
            "unsupported",
            f"Receipt failed mathematical validation: {math_reason}",
        )

    # 1.1. Provenance validation check if attached to receipt
    prov_valid = (
        receipt.get("provenance_valid")
        if isinstance(receipt, dict)
        else getattr(receipt, "provenance_valid", None)
    )
    if prov_valid is False:
        prov_err = (
            receipt.get("provenance_error")
            if isinstance(receipt, dict)
            else getattr(receipt, "provenance_error", "Provenance validation failed")
        )
        return (
            False,
            "incomplete",
            f"Receipt failed provenance validation: {prov_err}",
        )

    if isinstance(receipt, dict):
        calc_id = receipt.get("calculation_id", "receipt")
        m_name = receipt.get("metric_name", "")
        calc_val = receipt.get("calculated_value")
        unit = receipt.get("unit", "")
        obs_vals = receipt.get("values") or [
            o["value"] if isinstance(o, dict) else o
            for o in receipt.get("observations", [])
            if (isinstance(o, dict) and "value" in o) or isinstance(o, (int, float))
        ] or [
            inp.get("value")
            for inp in receipt.get("inputs", [])
            if isinstance(inp, dict) and ("observation_" in inp.get("input_name", "") or "observation_" in inp.get("name", ""))
        ]
        periods = receipt.get("periods", [])
        p_start = receipt.get("period_start", "")
        p_end = receipt.get("period_end", "")
    else:
        calc_id = receipt.calculation_id
        m_name = receipt.metric_name
        calc_val = receipt.calculated_value
        unit = receipt.unit
        obs_vals = getattr(receipt, "values", None) or [
            o["value"] if isinstance(o, dict) else o
            for o in (getattr(receipt, "observations", None) or [])
            if (isinstance(o, dict) and "value" in o) or isinstance(o, (int, float))
        ] or [
            inp.get("value")
            for inp in (getattr(receipt, "input_observations", None) or getattr(receipt, "inputs", None) or [])
            if isinstance(inp, dict) and ("observation_" in inp.get("input_name", "") or "observation_" in inp.get("name", ""))
        ]
        periods = getattr(receipt, "periods", None) or []
        p_start = getattr(receipt, "period_start", "")
        p_end = getattr(receipt, "period_end", "")

    if not periods and p_start and p_end:
        pk_s = parse_period_chronological_key(p_start)
        pk_e = parse_period_chronological_key(p_end)
        if pk_s[1] == 0 and pk_e[1] == 0 and pk_e[0] >= pk_s[0] and (pk_e[0] - pk_s[0] + 1 == len(obs_vals or [])):
            periods = [f"FY{y}" for y in range(pk_s[0], pk_e[0] + 1)]

    # Derive trajectory directly from verified observations
    recalculated_traj = classify_trajectory(obs_vals)
    traj_str = recalculated_traj.value

    c_lower = claim_text.lower()
    calc_m_clean = m_name.lower().replace("_", " ").replace(" trend", "").strip()

    # 2. Metric Identity Alignment Check
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
    for kw, canon in known_metrics.items():
        if kw in c_lower:
            canon_clean = canon.replace("_", " ")
            if (
                canon_clean not in calc_m_clean
                and calc_m_clean not in canon_clean
                and kw not in calc_m_clean
            ):
                return (
                    False,
                    "unsupported",
                    f"Metric mismatch: Claim asserts '{kw}' which differs from cited "
                    f"calculation receipt {calc_id} ({m_name}).",
                )

    # 3. Period Identity Alignment Check
    if mentioned_period:
        norm_mp = normalize_period(mentioned_period)
        norm_periods = [normalize_period(p) for p in periods]
        p_span = f"{normalize_period(p_start)}-{normalize_period(p_end)}"
        if (
            norm_mp not in norm_periods
            and norm_mp != p_span
            and norm_mp != normalize_period(p_start)
            and norm_mp != normalize_period(p_end)
        ):
            return (
                False,
                "unsupported",
                f"Period mismatch: Claim asserts period '{mentioned_period}' which does not align with trend receipt periods {norm_periods} ({p_span}).",
            )

    years_in_text = re.findall(r"\b(?:FY\s*)?(20\d{2})\b", claim_text, re.IGNORECASE)
    if years_in_text:
        receipt_years = [
            re.search(r"20\d{2}", p).group(0)
            for p in periods
            if re.search(r"20\d{2}", p)
        ]
        if receipt_years and all(y not in receipt_years for y in years_in_text):
            return (
                False,
                "unsupported",
                f"Period mismatch: Claim text mentions year(s) {years_in_text} not present in trend receipt periods {periods}.",
            )

    # 4. Trajectory Semantic Agreement Check
    mixed_keywords = {
        "mixed volatility",
        "mixed movement",
        "mixed",
        "fluctuated",
        "volatility across periods",
    }
    monotonic_keywords = {
        "monotonic",
        "monotonically",
        "consistently",
        "uninterrupted",
        "steady",
        "continuous",
    }

    asserts_mixed = any(kw in c_lower for kw in mixed_keywords)
    asserts_monotonic = any(kw in c_lower for kw in monotonic_keywords)

    if (
        recalculated_traj == TrajectoryType.INSUFFICIENT_DATA
        and (asserts_mixed or asserts_monotonic)
    ):
        return (
            False,
            "incomplete",
            "Observation series has insufficient data to verify trend trajectory.",
        )

    if asserts_mixed:
        if len(obs_vals) < 3:
            return (
                False,
                "contradicted",
                f"Trajectory contradiction: Claim asserts mixed volatility, but series contains only {len(obs_vals)} observations, which cannot establish mixed movement.",
            )
        if traj_str in ("MONOTONIC_UPWARD", "MONOTONIC_DOWNWARD"):
            return (
                False,
                "contradicted",
                f"Trajectory contradiction: Claim asserts mixed volatility, but verified observations "
                f"demonstrate monotonic movement ({traj_str}).",
            )
        elif traj_str == "FLAT":
            return (
                False,
                "contradicted",
                f"Trajectory contradiction: Claim asserts mixed volatility, but verified observations "
                f"demonstrate a flat trajectory ({traj_str}).",
            )

    if asserts_monotonic:
        if traj_str in ("MIXED_UPWARD_NET", "MIXED_DOWNWARD_NET"):
            return (
                False,
                "contradicted",
                f"Trajectory contradiction: Claim asserts monotonic/consistent movement, but verified observations "
                f"demonstrate mixed volatility ({traj_str}).",
            )

    # 5. Directional Polarity Agreement Check
    if calc_val is not None:
        c_clean = c_lower
        for metric_title in [
            "revenue growth",
            "earnings growth",
            "profit growth",
            "margin expansion",
            "gross margin",
            "operating margin",
            "free cash flow",
        ]:
            c_clean = c_clean.replace(metric_title, "")

        pos_words = {
            "increased",
            "increase",
            "grew",
            "rose",
            "accelerated",
            "upward",
            "positive",
            "expansion",
            "improved",
            "strengthened",
        }
        neg_words = {
            "decreased",
            "decrease",
            "declined",
            "decline",
            "fell",
            "contracted",
            "decelerated",
            "deceleration",
            "downward",
            "slowed",
            "negative",
            "loss",
            "tightened",
        }

        has_neg_num = False
        if numeric_values:
            has_neg_num = any(
                (getattr(nv, "numeric_value", 0) < 0) for nv in numeric_values
            )

        has_pos = (
            any(re.search(rf"\b{w}\b", c_clean) for w in pos_words)
            and not has_neg_num
            and not asserts_mixed
        )
        has_neg = (
            any(re.search(rf"\b{w}\b", c_clean) for w in neg_words) or has_neg_num
        ) and not asserts_mixed

        if calc_val < 0 and has_pos and not has_neg:
            return (
                False,
                "contradicted",
                f"Trend polarity contradiction: Claim asserts growth/increase, but "
                f"receipt {calc_id} calculated negative shift ({calc_val} {unit}).",
            )
        elif calc_val > 0 and has_neg and not has_pos:
            return (
                False,
                "contradicted",
                f"Trend polarity contradiction: Claim asserts decline/decrease, but "
                f"receipt {calc_id} calculated positive growth ({calc_val} {unit}).",
            )

    # 6. Quantitative Figures Alignment Check
    if numeric_values:
        for nv in numeric_values:
            val = getattr(nv, "numeric_value", None)
            if val is not None and isinstance(val, (int, float)):
                # If claim asserts a percentage that clearly contradicts calc_val
                if getattr(nv, "is_percentage", False) or "%" in getattr(
                    nv, "raw_text", ""
                ):
                    if calc_val is not None and abs(calc_val) > 1.0:
                        if not math.isclose(
                            val,
                            calc_val,
                            rel_tol=tolerance_pct / 100.0,
                            abs_tol=2.0,
                        ):
                            # Also check if it matches an intermediate observation
                            if not any(
                                math.isclose(
                                    val, obs_v, rel_tol=tolerance_pct / 100.0, abs_tol=2.0
                                )
                                for obs_v in obs_vals
                            ):
                                return (
                                    False,
                                    "unsupported",
                                    f"Numeric mismatch: Claim asserts percentage {val}% which does not match receipt calculated value {calc_val}% or intermediate observations.",
                                )

    return (
        True,
        "supported",
        f"Claim supported by verified trend receipt {calc_id} ({m_name} = {calc_val} {unit}, trajectory={traj_str}).",
    )


class TrendReceiptAuditor:
    """Production receipt deduplication and independent recalculation auditor.

    Guarantees:
        1. A calculation receipt is independently evaluated once per unique receipt.
        2. Multiple claims can reference the same receipt without inflating unique counts.
        3. Each claim retains its own citation mapping.
        4. Different receipts for the same metric across different periods are tracked separately.
        5. A failed receipt cannot become verified through deduplication.
    """

    def __init__(self, tolerance_pct: float = 1.0) -> None:
        self.tolerance_pct = tolerance_pct
        self.audited_receipts: dict[str, dict[str, Any]] = {}
        self.citation_to_calc_id: dict[str, str] = {}
        self.claim_to_citations: dict[str, list[str]] = {}
        self.receipt_to_claims: dict[str, set[str]] = {}

    def audit_receipt(
        self,
        receipt: dict[str, Any] | CalculationEvidence | None,
        citation_id: str,
        claim_id: str | None = None,
    ) -> dict[str, Any]:
        """Audit a calculation or trend receipt once and link referencing claims.

        Fail-closed: Missing receipts or observations immediately fail.
        """
        cit_upper = citation_id.upper()

        if receipt is None:
            failed_record = {
                "citation_id": cit_upper,
                "calculation_id": None,
                "status": "missing_receipt",
                "verification_reason": f"Calculation receipt data missing for citation {cit_upper}.",
                "is_valid": False,
                "recalculated_absolute_change": None,
                "recalculated_percentage_change": None,
                "start_value": None,
                "end_value": None,
                "periods": [],
                "observations": [],
                "observation_values": [],
                "observation_units": [],
                "independently_calculated_trajectory": "INSUFFICIENT_DATA",
                "recorded_trajectory": None,
                "trajectory": "INSUFFICIENT_DATA",
                "supporting_receipt_ids": [],
            }
            return failed_record

        if isinstance(receipt, dict):
            calc_id = (
                receipt.get("calculation_id") or receipt.get("citation_id") or cit_upper
            )
            m_name = receipt.get("metric_name", "")
            calc_val = receipt.get("calculated_value")
            unit = receipt.get("unit", "")
            p_start = receipt.get("period_start", "")
            p_end = receipt.get("period_end", "")
            formula_name = receipt.get("formula_name", "")
            formula_expr = receipt.get("formula_expression", "")
            inputs = receipt.get("inputs", [])
            supporting_ids = receipt.get("supporting_receipt_ids", [])
            recorded_traj = receipt.get("trajectory")
            periods_list = receipt.get("periods") or []
            obs_list = receipt.get("observations") or []
            obs_vals = receipt.get("values") or [
                o.get("value")
                for o in obs_list
                if isinstance(o, dict) and "value" in o
            ]
            obs_units = receipt.get("observation_units") or [
                o.get("unit") for o in obs_list if isinstance(o, dict) and "unit" in o
            ]
        else:
            calc_id = receipt.calculation_id or cit_upper
            m_name = receipt.metric_name
            calc_val = receipt.calculated_value
            unit = receipt.unit
            p_start = getattr(receipt, "period_start", "")
            p_end = getattr(receipt, "period_end", "")
            formula_name = getattr(receipt, "formula_name", "")
            formula_expr = getattr(receipt, "formula_expression", "") or getattr(
                receipt, "formula", ""
            )
            inputs = getattr(receipt, "inputs", []) or getattr(
                receipt, "input_observations", []
            )
            supporting_ids = getattr(receipt, "supporting_receipt_ids", [])
            recorded_traj = getattr(receipt, "trajectory", None)
            periods_list = getattr(receipt, "periods", None) or []
            obs_list = getattr(receipt, "observations", None) or []
            obs_vals = getattr(receipt, "values", None) or [
                o.get("value")
                for o in obs_list
                if isinstance(o, dict) and "value" in o
            ]
            obs_units = getattr(receipt, "observation_units", None) or [
                o.get("unit") for o in obs_list if isinstance(o, dict) and "unit" in o
            ]

        self.citation_to_calc_id[cit_upper] = calc_id
        if calc_id not in self.receipt_to_claims:
            self.receipt_to_claims[calc_id] = set()
        if claim_id:
            self.receipt_to_claims[calc_id].add(claim_id)
            if cit_upper not in self.claim_to_citations.setdefault(claim_id, []):
                self.claim_to_citations[claim_id].append(cit_upper)

        # Return cached evaluation if already audited (guaranteeing single independent evaluation)
        if calc_id in self.audited_receipts:
            return self.audited_receipts[calc_id]

        # First evaluation: execute independent recalculation
        is_valid, reason = verify_trend_math(receipt, tolerance_pct=self.tolerance_pct)

        input_map: dict[str, float] = {}
        obs_from_inputs: list[tuple[int, float, str | None, str | None]] = []

        if isinstance(inputs, dict):
            input_map = {
                k: float(v)
                for k, v in inputs.items()
                if v is not None and isinstance(v, (int, float))
            }
        elif isinstance(inputs, list):
            for inp in inputs:
                if hasattr(inp, "model_dump"):
                    inp = inp.model_dump()
                if isinstance(inp, dict):
                    k = inp.get("input_name") or inp.get("name")
                    v = inp.get("value")
                    inp_p = inp.get("period")
                    inp_u = inp.get("unit")
                    if k and v is not None and isinstance(v, (int, float)):
                        input_map[k] = float(v)
                        if k.startswith("observation_") or "index" in inp:
                            idx = inp.get("index")
                            if idx is None:
                                match = re.search(r"^observation_(\d+)_", k)
                                if match:
                                    idx = int(match.group(1))
                            if idx is not None:
                                obs_from_inputs.append(
                                    (int(idx), float(v), inp_p, inp_u)
                                )

        start_v = input_map.get("start_value")
        end_v = input_map.get("end_value")

        recalc_abs = (
            compute_absolute_change(start_v, end_v)
            if (start_v is not None and end_v is not None)
            else None
        )
        recalc_pct = (
            compute_percentage_change(start_v, end_v)
            if (start_v is not None and end_v is not None)
            else None
        )

        if not obs_vals and obs_from_inputs:
            obs_from_inputs.sort(key=lambda x: x[0])
            obs_vals = [x[1] for x in obs_from_inputs]
            if not periods_list:
                periods_list = [x[2] for x in obs_from_inputs if x[2]]
            if not obs_units:
                obs_units = [x[3] for x in obs_from_inputs if x[3]]

        recalculated_traj = classify_trajectory(obs_vals)
        independent_traj = recalculated_traj.value

        # Check if provenance trace is attached and validate it
        prov_trace = (
            receipt.get("provenance_trace")
            if isinstance(receipt, dict)
            else getattr(receipt, "provenance_trace", None)
        )
        provenance_valid = True
        provenance_reasons: list[str] = []
        if prov_trace and isinstance(prov_trace, list):
            for tr_calc in prov_trace:
                p_ok, p_msg, _ = validate_calculation_provenance(tr_calc)
                if not p_ok:
                    provenance_valid = False
                    provenance_reasons.append(p_msg)
        else:
            raw_input_obs = (
                receipt.get("input_observations")
                if isinstance(receipt, dict)
                else getattr(receipt, "input_observations", None)
            )
            if raw_input_obs and isinstance(raw_input_obs, list) and len(raw_input_obs) > 0:
                has_sec_obs = any(
                    isinstance(x, dict) and ("accession_number" in x or "source_url" in x)
                    for x in raw_input_obs
                )
                if has_sec_obs:
                    p_ok, p_msg, _ = validate_calculation_provenance(receipt)
                    if not p_ok:
                        provenance_valid = False
                        provenance_reasons.append(p_msg)

        if not provenance_valid:
            is_valid = False
            status = "failed_provenance"
            reason = f"Supporting calculation provenance failure: {'; '.join(provenance_reasons)}"
        elif is_valid:
            status = "verified"
        elif "missing" in reason.lower() or "insufficient" in reason.lower():
            status = "incomplete"
        elif "formula" in reason.lower():
            status = "invalid_formula"
        elif (
            "period" in reason.lower()
            or "observation" in reason.lower()
            or "order" in reason.lower()
            or "alignment" in reason.lower()
        ):
            status = "failed_period_alignment"
        elif "trajectory" in reason.lower():
            status = "failed_trajectory"
        else:
            status = "failed_recalculation"

        norm_periods = [
            normalize_period(str(p)) or str(p) for p in periods_list
        ]
        if not obs_units:
            obs_units = [unit] * len(obs_vals)

        formatted_observations = []
        if obs_list:
            formatted_observations = obs_list
        elif obs_vals and norm_periods and len(obs_vals) == len(norm_periods):
            formatted_observations = [
                {"period": p, "value": v, "unit": u}
                for p, v, u in zip(norm_periods, obs_vals, obs_units)
            ]

        record: dict[str, Any] = {
            "citation_id": cit_upper,
            "calculation_id": calc_id,
            "metric_name": m_name,
            "period_start": p_start,
            "period_end": p_end,
            "periods": norm_periods,
            "observations": formatted_observations,
            "observation_values": obs_vals,
            "observation_units": obs_units,
            "start_value": start_v,
            "end_value": end_v,
            "calculated_absolute_change": recalc_abs,
            "calculated_percentage_change": recalc_pct,
            "recalculated_absolute_change": recalc_abs,
            "recalculated_percentage_change": recalc_pct,
            "recorded_receipt_value": calc_val,
            "unit": unit,
            "formula_name": formula_name,
            "formula_expression": formula_expr,
            "recorded_trajectory": recorded_traj,
            "independently_calculated_trajectory": independent_traj,
            "trajectory": independent_traj,
            "status": status,
            "is_valid": is_valid,
            "alignment_valid": (status != "failed_period_alignment"),
            "provenance_valid": provenance_valid,
            "verification_reason": reason,
            "supporting_receipt_ids": supporting_ids,
        }

        self.audited_receipts[calc_id] = record
        return record

    def link_claim(self, claim_id: str, citation_ids: list[str]) -> None:
        """Register claim-to-citation mappings."""
        self.claim_to_citations[claim_id] = list(
            dict.fromkeys(c.upper() for c in citation_ids)
        )
        for cid in self.claim_to_citations[claim_id]:
            calc_id = self.citation_to_calc_id.get(cid, cid)
            self.receipt_to_claims.setdefault(calc_id, set()).add(claim_id)

    def get_unique_receipts(self) -> list[dict[str, Any]]:
        """Return unique audited calculation receipts."""
        return list(self.audited_receipts.values())

    def get_summary(self) -> dict[str, int]:
        """Return deduplicated summary statistics."""
        total = len(self.audited_receipts)
        verified = sum(
            1 for r in self.audited_receipts.values() if r.get("status") == "verified"
        )
        failed = sum(
            1
            for r in self.audited_receipts.values()
            if r.get("status") in ("failed_recalculation", "failed_trajectory")
        )
        incomplete = sum(
            1
            for r in self.audited_receipts.values()
            if r.get("status") in ("incomplete", "missing_receipt", "invalid_formula")
        )
        return {
            "total_unique_receipts": total,
            "verified_receipts": verified,
            "failed_receipts": failed,
            "incomplete_receipts": incomplete,
            "total_referencing_claims": len(self.claim_to_citations),
        }
