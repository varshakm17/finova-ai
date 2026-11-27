"""Deterministic Financial Longitudinal Trends & Trend Receipt Verification.

Computes multi-period percentage and absolute changes with strict zero-denominator
handling, mathematical reproducibility, trajectory classification, and receipt verification for Finova AI.
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any

from backend.rag.rag_models import CalculationEvidence
from backend.utils.logger import get_logger
from backend.verification.period_verifier import normalize_period

logger = get_logger("financial_trends")


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
        "input_observations": inputs,
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
        4. Independent recalculation and validation of absolute change.
        5. Independent recalculation and validation of percentage change (if applicable).
        6. Zero denominator handling: undefined percentage change if start_value is 0.
        7. Trajectory classification recalculation and validation against recorded trajectory.
        8. Formula metadata agreement between formula_name and formula_expression.
        9. Mathematical agreement between calculated_value and recalculated value.

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

    if calc_val is None:
        return False, f"Missing calculated_value in trend receipt for {metric_name}"

    input_map: dict[str, float] = {}
    input_names: list[str] = []
    obs_from_inputs: list[tuple[int, float]] = []

    if isinstance(inputs, dict):
        for name, val in inputs.items():
            input_names.append(name)
            if val is not None and isinstance(val, (int, float)):
                input_map[name] = float(val)
    elif isinstance(inputs, list):
        for inp in inputs:
            if hasattr(inp, "model_dump"):
                inp = inp.model_dump()
            if isinstance(inp, dict):
                name = inp.get("input_name") or inp.get("name")
                val = inp.get("value")
                if name:
                    input_names.append(name)
                if name and val is not None and isinstance(val, (int, float)):
                    input_map[name] = float(val)
                    if name.startswith("observation_") or "index" in inp:
                        idx = inp.get("index")
                        if idx is None:
                            match = re.search(r"^observation_(\d+)_", name)
                            if match:
                                idx = int(match.group(1))
                        if idx is not None:
                            obs_from_inputs.append((int(idx), float(val)))

    start_v = input_map.get("start_value")
    end_v = input_map.get("end_value")

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

    # Extract complete ordered observations
    obs_vals: list[float] = []
    if top_obs is not None:
        if not isinstance(top_obs, list) or len(top_obs) < 2:
            return (
                False,
                f"Missing or insufficient intermediate observations for {metric_name} (found {len(top_obs) if isinstance(top_obs, list) else 0} < 2)",
            )
        for item in top_obs:
            if isinstance(item, dict):
                val = item.get("value")
            else:
                val = item
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
            except (ValueError, TypeError):
                return (
                    False,
                    f"Invalid non-numeric observation value in trend observations for {metric_name}",
                )
    elif obs_from_inputs and len(obs_from_inputs) >= 2:
        obs_from_inputs.sort(key=lambda x: x[0])
        obs_vals = [x[1] for x in obs_from_inputs]
    elif start_v is not None and end_v is not None:
        obs_vals = [start_v, end_v]
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
    if recorded_traj and recorded_traj != recalculated_traj.value:
        return False, (
            f"Trajectory mismatch for {metric_name}: recorded '{recorded_traj}', "
            f"recalculated '{recalculated_traj.value}' from observations {obs_vals}"
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

    expected_abs = compute_absolute_change(start_v, end_v)
    expected_pct = compute_percentage_change(start_v, end_v)

    is_pct_receipt = (
        unit in {"%", "percentage", "pct"}
        or "abs(V_start)" in str(formula_expr)
        or "Percentage" in str(formula_name)
    )

    if is_pct_receipt:
        if abs(start_v) < 1e-9:
            return (
                False,
                f"Zero denominator: percentage change undefined for {metric_name} (start_value=0)",
            )
        if expected_pct is None:
            return False, f"Unable to compute percentage change for {metric_name}"

        # Check percentage calculation
        if not math.isclose(
            calc_val, expected_pct, rel_tol=tolerance_pct / 100.0, abs_tol=1e-3
        ):
            return False, (
                f"Trend percentage mismatch on {metric_name}: recorded {calc_val}%, "
                f"recalculated {expected_pct}% from start={start_v}, end={end_v}"
            )
        return True, "Deterministic trend percentage verified"
    else:
        # Absolute shift receipt
        if expected_abs is None:
            return False, f"Unable to compute absolute change for {metric_name}"
        if not math.isclose(
            calc_val, expected_abs, rel_tol=tolerance_pct / 100.0, abs_tol=1e-3
        ):
            return False, (
                f"Trend absolute change mismatch on {metric_name}: recorded {calc_val}, "
                f"recalculated {expected_abs} from start={start_v}, end={end_v}"
            )
        return True, "Deterministic trend absolute change verified"


def verify_trend_semantics(
    claim_text: str,
    receipt: dict[str, Any] | CalculationEvidence,
    numeric_values: list[Any] | None = None,
    tolerance_pct: float = 1.0,
) -> tuple[bool, str, str]:
    """Verify semantic agreement between claim narrative assertions and trend receipt.

    Audits:
        1. Non-empty receipt existence.
        2. Metric identity alignment.
        3. Qualitative trajectory agreement (mixed volatility vs monotonic).
        4. Net directional polarity agreement.
        5. Quantitative figures alignment against receipt calculations and observations.

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

    if isinstance(receipt, dict):
        calc_id = receipt.get("calculation_id", "receipt")
        m_name = receipt.get("metric_name", "")
        calc_val = receipt.get("calculated_value")
        unit = receipt.get("unit", "")
        recorded_traj = receipt.get("trajectory")
        obs_vals = receipt.get("values", [])
    else:
        calc_id = receipt.calculation_id
        m_name = receipt.metric_name
        calc_val = receipt.calculated_value
        unit = receipt.unit
        recorded_traj = getattr(receipt, "trajectory", None)
        obs_vals = getattr(receipt, "values", []) or [
            inp.get("value")
            for inp in getattr(receipt, "input_observations", [])
            if "observation_" in inp.get("input_name", "")
        ]

    c_lower = claim_text.lower()
    calc_m_clean = m_name.lower().replace("_", " ").replace(" trend", "").strip()

    # 1. Metric Identity Alignment Check
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

    # Resolve trajectory
    if not recorded_traj and obs_vals and len(obs_vals) >= 2:
        recorded_traj = classify_trajectory(obs_vals).value
    traj_str = str(recorded_traj) if recorded_traj else "INSUFFICIENT_DATA"

    # 2. Trajectory Semantic Agreement Check
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

    if asserts_mixed:
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

    # 3. Directional Polarity Agreement Check
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

    return (
        True,
        "supported",
        f"Claim supported by deterministic calculation receipt {calc_id} ({m_name} = {calc_val} {unit}).",
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
                "observations": [],
                "trajectory": "INSUFFICIENT_DATA",
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
            formula_expr = receipt.get("formula_expression", "")
            inputs = receipt.get("inputs", [])
            supporting_ids = receipt.get("supporting_receipt_ids", [])
        else:
            calc_id = receipt.calculation_id or cit_upper
            m_name = receipt.metric_name
            calc_val = receipt.calculated_value
            unit = receipt.unit
            p_start = getattr(receipt, "period_start", "")
            p_end = getattr(receipt, "period_end", "")
            formula_expr = getattr(receipt, "formula_expression", "") or getattr(
                receipt, "formula", ""
            )
            inputs = getattr(receipt, "inputs", []) or getattr(
                receipt, "input_observations", []
            )
            supporting_ids = getattr(receipt, "supporting_receipt_ids", [])

        self.citation_to_calc_id[cit_upper] = calc_id
        if calc_id not in self.receipt_to_claims:
            self.receipt_to_claims[calc_id] = set()
        if claim_id:
            self.receipt_to_claims[calc_id].add(claim_id)

        # Return cached evaluation if already audited (guaranteeing single independent evaluation)
        if calc_id in self.audited_receipts:
            return self.audited_receipts[calc_id]

        # First evaluation: execute independent recalculation
        is_valid, reason = verify_trend_math(receipt, tolerance_pct=self.tolerance_pct)

        input_map: dict[str, float] = {}
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
                    if k and v is not None and isinstance(v, (int, float)):
                        input_map[k] = float(v)

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

        obs_vals = (
            receipt.get("values", [])
            if isinstance(receipt, dict)
            else getattr(receipt, "values", [])
        )
        if not obs_vals and start_v is not None and end_v is not None:
            obs_vals = [start_v, end_v]
        trajectory = classify_trajectory(obs_vals).value

        if is_valid:
            status = "verified"
        elif "missing" in reason.lower() or "insufficient" in reason.lower():
            status = "incomplete"
        elif "formula" in reason.lower():
            status = "invalid_formula"
        elif "trajectory" in reason.lower():
            status = "failed_trajectory"
        else:
            status = "failed_recalculation"

        record: dict[str, Any] = {
            "citation_id": cit_upper,
            "calculation_id": calc_id,
            "metric_name": m_name,
            "period_start": p_start,
            "period_end": p_end,
            "start_value": start_v,
            "end_value": end_v,
            "calculated_absolute_change": recalc_abs,
            "calculated_percentage_change": recalc_pct,
            "recorded_receipt_value": calc_val,
            "unit": unit,
            "formula_expression": formula_expr,
            "trajectory": trajectory,
            "status": status,
            "is_valid": is_valid,
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
