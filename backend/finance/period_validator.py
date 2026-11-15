"""Financial Period and Unit Compatibility Validator.

Validates temporal alignment, period equivalence, unit compatibility,
and denominator non-zero conditions prior to executing financial formulas.
"""

from datetime import datetime

from backend.data.data_normalizer import FinancialObservation


class PeriodValidationError(Exception):
    """Raised when financial observations violate period or unit compatibility constraints."""


def validate_units(
    observations: list[FinancialObservation],
    expected_unit: str = "USD",
) -> tuple[bool, str | None]:
    """Verify that all observations share a compatible currency / unit of measure.

    Args:
        observations: Input financial observations to validate.
        expected_unit: Target unit (default: 'USD').

    Returns:
        tuple[bool, str | None]: (is_valid, error_reason).
    """
    if not observations:
        return True, None

    units = {obs.unit.upper().strip() for obs in observations if obs.unit}
    if len(units) > 1:
        return (
            False,
            f"Unit incompatibility: cannot combine multiple distinct units {sorted(units)}.",
        )

    if expected_unit and units:
        current_unit = next(iter(units))
        if current_unit != expected_unit.upper():
            return (
                False,
                f"Unexpected unit '{current_unit}'; expected monetary unit '{expected_unit}'.",
            )

    return True, None


def validate_flow_period_alignment(
    obs_a: FinancialObservation,
    obs_b: FinancialObservation,
) -> tuple[bool, str | None]:
    """Verify that two flow statement observations represent the exact same reporting duration and dates.

    Args:
        obs_a: First flow statement observation (e.g. Gross Profit).
        obs_b: Second flow statement observation (e.g. Revenue).

    Returns:
        tuple[bool, str | None]: (is_valid, error_reason).
    """
    if obs_a.period_type != obs_b.period_type:
        return (
            False,
            f"Period type mismatch: '{obs_a.metric_name}' is {obs_a.period_type} but '{obs_b.metric_name}' is {obs_b.period_type}.",
        )

    if obs_a.period_type == "ytd" or obs_b.period_type == "ytd":
        return (
            False,
            "Cumulative Year-To-Date (YTD) flow metrics cannot be conflated with standalone periodic metrics.",
        )

    if obs_a.period_end != obs_b.period_end:
        return (
            False,
            f"Period end date mismatch: {obs_a.period_end} vs {obs_b.period_end}.",
        )

    return True, None


def validate_instant_balance_sheet_alignment(
    balance_sheet_obs: FinancialObservation,
    target_period_end: str,
    tolerance_days: int = 7,
) -> tuple[bool, str | None]:
    """Verify that a balance sheet point-in-time observation matches the closing date of the income statement.

    Args:
        balance_sheet_obs: Instant balance sheet observation.
        target_period_end: Target period end date (YYYY-MM-DD).
        tolerance_days: Allowed calendar day discrepancy for floating 52/53-week fiscal year ends.

    Returns:
        tuple[bool, str | None]: (is_valid, error_reason).
    """
    if balance_sheet_obs.period_type != "instant":
        return (
            False,
            f"Balance sheet metric '{balance_sheet_obs.metric_name}' must have period_type 'instant', got '{balance_sheet_obs.period_type}'.",
        )

    if balance_sheet_obs.period_end == target_period_end:
        return True, None

    try:
        bs_date = datetime.strptime(balance_sheet_obs.period_end, "%Y-%m-%d").date()
        target_date = datetime.strptime(target_period_end, "%Y-%m-%d").date()
        diff = abs((bs_date - target_date).days)
        if diff <= tolerance_days:
            return True, None
        return (
            False,
            f"Date discrepancy: balance sheet date {balance_sheet_obs.period_end} differs from {target_period_end} by {diff} days (tolerance: {tolerance_days} days).",
        )
    except (ValueError, TypeError) as exc:
        return False, f"Invalid date formatting: {exc}"


def find_opening_balance_observation(
    metric_name: str,
    closing_period_start: str | None,
    candidate_observations: list[FinancialObservation],
    tolerance_days: int = 14,
) -> FinancialObservation | None:
    """Find the matching opening balance sheet observation for an income statement period.

    Opening balance corresponds to the balance sheet date as of the period start of the income
    statement, or the closing balance sheet of the immediately preceding fiscal year.

    Args:
        metric_name: Canonical metric (e.g. 'Total Assets', 'Stockholders\' Equity').
        closing_period_start: Start date of the flow period (YYYY-MM-DD).
        candidate_observations: List of all available instant observations for the company.
        tolerance_days: Calendar tolerance for 52/53-week floating boundaries.

    Returns:
        FinancialObservation | None: Matching opening balance observation, or None if unavailable.
    """
    if not closing_period_start:
        return None

    try:
        target_start = datetime.strptime(closing_period_start, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    # Filter candidate instant observations for the same metric
    candidates = [
        obs
        for obs in candidate_observations
        if obs.metric_name.lower() == metric_name.lower()
        and obs.period_type == "instant"
    ]

    best_match: FinancialObservation | None = None
    min_diff = 999999

    for c in candidates:
        try:
            c_date = datetime.strptime(c.period_end, "%Y-%m-%d").date()
            diff = abs((c_date - target_start).days)
            if diff <= tolerance_days and diff < min_diff:
                min_diff = diff
                best_match = c
        except (ValueError, TypeError):
            continue

    return best_match
