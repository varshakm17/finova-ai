"""Deterministic Financial Longitudinal Trends & Trend Receipt Verification.

Computes multi-period percentage and absolute changes with strict zero-denominator
handling, mathematical reproducibility, and receipt verification for Finova AI.
"""

from __future__ import annotations

import math
import re
from typing import Any

from backend.rag.rag_models import CalculationEvidence
from backend.utils.logger import get_logger
from backend.verification.period_verifier import normalize_period

logger = get_logger("financial_trends")


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

    Ensures mathematical agreement between formula, calculated_value, unit,
    and recorded input observations.
    """
    if not metric_name or len(values) < 2 or len(periods) < 2:
        logger.warning(
            "Incomplete inputs for trend receipt %s: values=%s, periods=%s",
            metric_name,
            values,
            periods,
        )
        return None

    start_val = values[0]
    end_val = values[-1]
    if start_val is None or end_val is None:
        return None

    pct_chg = compute_percentage_change(start_val, end_val)
    abs_chg = compute_absolute_change(start_val, end_val)

    if abs_chg is None:
        return None

    p_start = normalize_period(str(periods[0])) or str(periods[0])
    p_end = normalize_period(str(periods[-1])) or str(periods[-1])
    p_label = f"{p_start}-{p_end}"

    clean_metric_id = re.sub(r"[^a-zA-Z0-9_]", "_", metric_name)
    clean_p_label = re.sub(r"[^a-zA-Z0-9_]", "_", p_label)
    calc_id = f"calc_trend_{clean_metric_id}_{clean_p_label}"

    inputs: list[dict[str, Any]] = [
        {"input_name": "start_value", "value": start_val, "unit": unit},
        {"input_name": "end_value", "value": end_val, "unit": unit},
        {"input_name": "absolute_change", "value": abs_chg, "unit": unit},
    ]

    if pct_chg is not None:
        inputs.append(
            {"input_name": "percentage_change", "value": pct_chg, "unit": "%"}
        )
        # Default trend representation when percentage growth is computable
        calculated_value = pct_chg
        receipt_unit = "%"
        formula_name = "Multi-Period Percentage Growth Analysis"
        formula_expression = "((V_end - V_start) / abs(V_start)) * 100"
    else:
        # Zero denominator case: explicitly label as absolute net shift, never percentage!
        calculated_value = abs_chg
        receipt_unit = unit
        formula_name = "Multi-Period Absolute Net Shift"
        formula_expression = "V_end - V_start"

    return {
        "citation_id": citation_id,
        "calculation_id": calc_id,
        "metric_name": f"{metric_name} Trend",
        "formula_name": formula_name,
        "formula_expression": formula_expression,
        "calculated_value": calculated_value,
        "unit": receipt_unit,
        "fiscal_year": p_end,
        "fiscal_period": "MULTI",
        "period_start": p_start,
        "period_end": p_end,
        "inputs": inputs,
        "supporting_receipt_ids": supporting_receipt_ids or [],
    }


def verify_trend_math(
    receipt: dict[str, Any] | CalculationEvidence,
    tolerance_pct: float = 1.0,
) -> tuple[bool, str]:
    """Independently audit and recalculate a trend receipt from its recorded inputs.

    Returns:
        (is_valid, reason)
    """
    if isinstance(receipt, dict):
        calc_val = receipt.get("calculated_value")
        unit = receipt.get("unit", "")
        formula = receipt.get("formula_expression", "")
        inputs = receipt.get("inputs", [])
        metric_name = receipt.get("metric_name", "Trend")
    else:
        calc_val = receipt.calculated_value
        unit = receipt.unit
        formula = receipt.formula_expression
        inputs = getattr(receipt, "inputs", []) or getattr(receipt, "input_observations", [])
        metric_name = receipt.metric_name

    input_map: dict[str, float] = {}
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
                if name and val is not None and isinstance(val, (int, float)):
                    input_map[name] = float(val)

    start_v = input_map.get("start_value")
    end_v = input_map.get("end_value")

    if start_v is None or end_v is None:
        return False, f"Missing start_value or end_value in trend inputs for {metric_name}"

    expected_abs = compute_absolute_change(start_v, end_v)
    expected_pct = compute_percentage_change(start_v, end_v)

    is_pct_receipt = unit in {"%", "percentage", "pct"} or "abs(V_start)" in formula

    if is_pct_receipt:
        if abs(start_v) < 1e-9:
            return False, f"Zero denominator: percentage change undefined for {metric_name} (start_value=0)"
        if expected_pct is None:
            return False, f"Unable to compute percentage change for {metric_name}"

        # Check percentage calculation
        if not math.isclose(calc_val, expected_pct, rel_tol=tolerance_pct / 100.0, abs_tol=1e-3):
            return False, (
                f"Trend percentage mismatch on {metric_name}: recorded {calc_val}%, "
                f"recalculated {expected_pct}% from start={start_v}, end={end_v}"
            )
        return True, "Deterministic trend percentage verified"
    else:
        # Absolute shift receipt
        if expected_abs is None:
            return False, f"Unable to compute absolute change for {metric_name}"
        if not math.isclose(calc_val, expected_abs, rel_tol=tolerance_pct / 100.0, abs_tol=1e-3):
            return False, (
                f"Trend absolute change mismatch on {metric_name}: recorded {calc_val}, "
                f"recalculated {expected_abs} from start={start_v}, end={end_v}"
            )
        return True, "Deterministic trend absolute change verified"
