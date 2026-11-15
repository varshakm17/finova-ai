"""Pure Deterministic Financial Calculation Engine.

Executes mathematical formulas for financial ratios, profitability margins,
and cash flow metrics using pure Python arithmetic without external API or LLM dependencies.
"""


class CalculationEngine:
    """Pure arithmetic engine for standard financial analysis indicators."""

    @staticmethod
    def calculate_revenue_growth(
        current_revenue: float, previous_revenue: float
    ) -> float:
        """Calculate year-over-year or period-over-period percentage revenue growth.

        Formula:
            ((Current Revenue - Previous Revenue) / Previous Revenue) * 100

        Raises:
            ZeroDivisionError: If previous revenue is zero.
        """
        if previous_revenue == 0:
            raise ZeroDivisionError(
                "Previous period revenue is zero; percentage growth undefined."
            )
        return ((current_revenue - previous_revenue) / previous_revenue) * 100.0

    @staticmethod
    def calculate_gross_profit_margin(gross_profit: float, revenue: float) -> float:
        """Calculate Gross Profit Margin percentage.

        Formula:
            (Gross Profit / Revenue) * 100

        Raises:
            ZeroDivisionError: If revenue is zero.
        """
        if revenue == 0:
            raise ZeroDivisionError("Revenue is zero; gross profit margin undefined.")
        return (gross_profit / revenue) * 100.0

    @staticmethod
    def calculate_operating_profit_margin(
        operating_income: float, revenue: float
    ) -> float:
        """Calculate Operating Profit Margin percentage.

        Formula:
            (Operating Income / Revenue) * 100

        Raises:
            ZeroDivisionError: If revenue is zero.
        """
        if revenue == 0:
            raise ZeroDivisionError(
                "Revenue is zero; operating profit margin undefined."
            )
        return (operating_income / revenue) * 100.0

    @staticmethod
    def calculate_net_profit_margin(net_income: float, revenue: float) -> float:
        """Calculate Net Profit Margin percentage.

        Formula:
            (Net Income / Revenue) * 100

        Raises:
            ZeroDivisionError: If revenue is zero.
        """
        if revenue == 0:
            raise ZeroDivisionError("Revenue is zero; net profit margin undefined.")
        return (net_income / revenue) * 100.0

    @staticmethod
    def calculate_current_ratio(
        current_assets: float, current_liabilities: float
    ) -> float:
        """Calculate Current Ratio (Liquidity).

        Formula:
            Current Assets / Current Liabilities

        Raises:
            ZeroDivisionError: If current liabilities is zero.
        """
        if current_liabilities == 0:
            raise ZeroDivisionError(
                "Current liabilities is zero; current ratio undefined."
            )
        return current_assets / current_liabilities

    @staticmethod
    def calculate_debt_to_equity(
        total_debt: float, stockholders_equity: float
    ) -> float:
        """Calculate Total Debt to Equity Ratio.

        Formula:
            Total Debt / Stockholders' Equity

        Raises:
            ZeroDivisionError: If stockholders' equity is zero.
        """
        if stockholders_equity == 0:
            raise ZeroDivisionError(
                "Stockholders' equity is zero; debt-to-equity ratio undefined."
            )
        return total_debt / stockholders_equity

    @staticmethod
    def calculate_long_term_debt_to_equity(
        long_term_debt: float, stockholders_equity: float
    ) -> float:
        """Calculate Long-Term Debt to Equity Ratio.

        Formula:
            Long-Term Debt / Stockholders' Equity

        Raises:
            ZeroDivisionError: If stockholders' equity is zero.
        """
        if stockholders_equity == 0:
            raise ZeroDivisionError(
                "Stockholders' equity is zero; long-term debt-to-equity ratio undefined."
            )
        return long_term_debt / stockholders_equity

    @staticmethod
    def calculate_return_on_assets(
        net_income: float, opening_total_assets: float, closing_total_assets: float
    ) -> float:
        """Calculate Return on Assets (ROA) percentage using average total assets.

        Formula:
            (Net Income / Average Total Assets) * 100
        Where:
            Average Total Assets = (Opening Total Assets + Closing Total Assets) / 2

        Raises:
            ZeroDivisionError: If average total assets is zero.
            ValueError: If average total assets is negative.
        """
        average_assets = (opening_total_assets + closing_total_assets) / 2.0
        if average_assets == 0:
            raise ZeroDivisionError("Average total assets is zero; ROA undefined.")
        if average_assets < 0:
            raise ValueError("Average total assets cannot be negative.")
        return (net_income / average_assets) * 100.0

    @staticmethod
    def calculate_return_on_equity(
        net_income: float, opening_equity: float, closing_equity: float
    ) -> float:
        """Calculate Return on Equity (ROE) percentage using average stockholders' equity.

        Formula:
            (Net Income / Average Stockholders' Equity) * 100
        Where:
            Average Stockholders' Equity = (Opening Equity + Closing Equity) / 2

        Raises:
            ZeroDivisionError: If average stockholders' equity is zero.
        """
        average_equity = (opening_equity + closing_equity) / 2.0
        if average_equity == 0:
            raise ZeroDivisionError(
                "Average stockholders' equity is zero; ROE undefined."
            )
        return (net_income / average_equity) * 100.0

    @staticmethod
    def calculate_operating_cash_flow_margin(
        operating_cash_flow: float, revenue: float
    ) -> float:
        """Calculate Operating Cash Flow Margin percentage.

        Formula:
            (Operating Cash Flow / Revenue) * 100

        Raises:
            ZeroDivisionError: If revenue is zero.
        """
        if revenue == 0:
            raise ZeroDivisionError(
                "Revenue is zero; operating cash flow margin undefined."
            )
        return (operating_cash_flow / revenue) * 100.0

    @staticmethod
    def calculate_free_cash_flow(
        operating_cash_flow: float, capital_expenditures: float
    ) -> tuple[float, float, str]:
        """Calculate Free Cash Flow with explicit CapEx sign normalization.

        Formula:
            Operating Cash Flow - Normalized CapEx
        Where:
            Normalized CapEx = abs(Capital Expenditures)

        Returns:
            tuple[float, float, str]: (free_cash_flow, normalized_capex, normalization_explanation).
        """
        normalized_capex = abs(capital_expenditures)
        fcf = operating_cash_flow - normalized_capex
        explanation = (
            f"Normalized CapEx to positive cash outflow magnitude abs({capital_expenditures:g}) = "
            f"{normalized_capex:g} before subtraction to ensure cash outflow decreases Free Cash Flow."
        )
        return fcf, normalized_capex, explanation
