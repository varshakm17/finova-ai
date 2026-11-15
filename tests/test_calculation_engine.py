"""Unit tests for deterministic financial CalculationEngine formulas."""

import pytest

from backend.finance.calculation_engine import CalculationEngine


def test_revenue_growth_formula() -> None:
    """Verify Revenue Growth formula: ((Current - Previous) / Previous) * 100."""
    # Positive growth: $110M vs $100M -> +10.0%
    growth = CalculationEngine.calculate_revenue_growth(110.0, 100.0)
    assert growth == pytest.approx(10.0, rel=1e-5)

    # Negative contraction: $80M vs $100M -> -20.0%
    contraction = CalculationEngine.calculate_revenue_growth(80.0, 100.0)
    assert contraction == pytest.approx(-20.0, rel=1e-5)

    # Division by zero
    with pytest.raises(ZeroDivisionError, match="Previous period revenue is zero"):
        CalculationEngine.calculate_revenue_growth(100.0, 0.0)


def test_gross_profit_margin_formula() -> None:
    """Verify Gross Profit Margin formula: (Gross Profit / Revenue) * 100."""
    margin = CalculationEngine.calculate_gross_profit_margin(44.0, 100.0)
    assert margin == pytest.approx(44.0, rel=1e-5)

    # Zero revenue
    with pytest.raises(ZeroDivisionError, match="Revenue is zero"):
        CalculationEngine.calculate_gross_profit_margin(50.0, 0.0)


def test_operating_profit_margin_formula() -> None:
    """Verify Operating Profit Margin formula: (Operating Income / Revenue) * 100."""
    margin = CalculationEngine.calculate_operating_profit_margin(30.0, 100.0)
    assert margin == pytest.approx(30.0, rel=1e-5)

    # Operating loss
    loss_margin = CalculationEngine.calculate_operating_profit_margin(-15.0, 100.0)
    assert loss_margin == pytest.approx(-15.0, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Revenue is zero"):
        CalculationEngine.calculate_operating_profit_margin(30.0, 0.0)


def test_net_profit_margin_formula() -> None:
    """Verify Net Profit Margin formula: (Net Income / Revenue) * 100."""
    margin = CalculationEngine.calculate_net_profit_margin(25.0, 100.0)
    assert margin == pytest.approx(25.0, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Revenue is zero"):
        CalculationEngine.calculate_net_profit_margin(25.0, 0.0)


def test_current_ratio_formula() -> None:
    """Verify Current Ratio formula: Current Assets / Current Liabilities."""
    ratio = CalculationEngine.calculate_current_ratio(150.0, 100.0)
    assert ratio == pytest.approx(1.5, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Current liabilities is zero"):
        CalculationEngine.calculate_current_ratio(150.0, 0.0)


def test_debt_to_equity_formulas() -> None:
    """Verify Total Debt to Equity and Long-Term Debt to Equity formulas."""
    # Total Debt / Equity
    de_ratio = CalculationEngine.calculate_debt_to_equity(200.0, 100.0)
    assert de_ratio == pytest.approx(2.0, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Stockholders' equity is zero"):
        CalculationEngine.calculate_debt_to_equity(200.0, 0.0)

    # Long-Term Debt / Equity
    lt_de = CalculationEngine.calculate_long_term_debt_to_equity(120.0, 100.0)
    assert lt_de == pytest.approx(1.2, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Stockholders' equity is zero"):
        CalculationEngine.calculate_long_term_debt_to_equity(120.0, 0.0)


def test_return_on_assets_formula() -> None:
    """Verify Return on Assets (ROA) formula: (Net Income / Average Assets) * 100."""
    # Net Income = $10M, Opening Assets = $90M, Closing Assets = $110M -> Avg = $100M -> ROA = 10.0%
    roa = CalculationEngine.calculate_return_on_assets(
        net_income=10.0,
        opening_total_assets=90.0,
        closing_total_assets=110.0,
    )
    assert roa == pytest.approx(10.0, rel=1e-5)

    # Zero average assets
    with pytest.raises(ZeroDivisionError, match="Average total assets is zero"):
        CalculationEngine.calculate_return_on_assets(10.0, -50.0, 50.0)

    # Negative average assets
    with pytest.raises(ValueError, match="Average total assets cannot be negative"):
        CalculationEngine.calculate_return_on_assets(10.0, -120.0, -80.0)


def test_return_on_equity_formula() -> None:
    """Verify Return on Equity (ROE) formula: (Net Income / Average Equity) * 100."""
    # Net Income = $20M, Opening Equity = $70M, Closing Equity = $90M -> Avg = $80M -> ROE = 25.0%
    roe = CalculationEngine.calculate_return_on_equity(
        net_income=20.0,
        opening_equity=70.0,
        closing_equity=90.0,
    )
    assert roe == pytest.approx(25.0, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Average stockholders' equity is zero"):
        CalculationEngine.calculate_return_on_equity(20.0, -40.0, 40.0)


def test_operating_cash_flow_margin_formula() -> None:
    """Verify Operating Cash Flow Margin formula: (OCF / Revenue) * 100."""
    margin = CalculationEngine.calculate_operating_cash_flow_margin(35.0, 100.0)
    assert margin == pytest.approx(35.0, rel=1e-5)

    with pytest.raises(ZeroDivisionError, match="Revenue is zero"):
        CalculationEngine.calculate_operating_cash_flow_margin(35.0, 0.0)


def test_free_cash_flow_capex_sign_normalization() -> None:
    """Verify Free Cash Flow normalizes CapEx sign so cash outflow reduces FCF."""
    ocf = 100.0

    # Case A: CapEx reported as positive magnitude (standard SEC payment tag, e.g. +30)
    fcf_a, norm_capex_a, expl_a = CalculationEngine.calculate_free_cash_flow(
        operating_cash_flow=ocf,
        capital_expenditures=30.0,
    )
    assert fcf_a == 70.0
    assert norm_capex_a == 30.0
    assert "Normalized CapEx" in expl_a

    # Case B: CapEx reported as negative outflow (e.g. -30)
    # If not normalized, subtracting -30 would yield 100 - (-30) = 130 (an arithmetic error!)
    fcf_b, norm_capex_b, expl_b = CalculationEngine.calculate_free_cash_flow(
        operating_cash_flow=ocf,
        capital_expenditures=-30.0,
    )
    assert fcf_b == 70.0
    assert norm_capex_b == 30.0
    assert "abs(-30)" in expl_b
