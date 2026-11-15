"""Pydantic Models and Receipts for Deterministic Financial Calculations.

Defines schemas for input observation provenance, calculation receipts,
and API request/response structures.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

CalculationStatus = Literal["calculated", "unavailable", "invalid_inputs"]


class CalculationInputObservation(BaseModel):
    """Provenance record of a single financial observation used in a calculation."""

    metric_name: str = Field(
        ..., description="Canonical metric name (e.g. Revenue, Net Income)"
    )
    value: float = Field(..., description="Reported numeric value")
    unit: str = Field(..., description="Reported unit of measure (e.g. USD, shares)")
    period_start: str | None = Field(
        None, description="Start date of period (YYYY-MM-DD)"
    )
    period_end: str = Field(
        ..., description="End date / point-in-time balance sheet date (YYYY-MM-DD)"
    )
    period_type: str = Field(
        ..., description="Temporal classification ('annual', 'quarterly', 'instant')"
    )
    filing_type: str | None = Field(
        None, description="Source SEC form code (e.g. 10-K, 10-Q)"
    )
    accession_number: str | None = Field(
        None, description="SEC EDGAR unique filing accession number"
    )
    source_url: str | None = Field(
        None, description="Canonical SEC archive link to primary document"
    )
    normalization_note: str | None = Field(
        None,
        description="Any adjustment note applied to input (e.g. CapEx sign convention)",
    )


class CalculationReceipt(BaseModel):
    """Transparent, verifiable calculation receipt with complete formula and input provenance."""

    calculation_id: str = Field(..., description="Unique calculation identifier")
    ticker: str = Field(..., description="Stock ticker symbol (e.g. AAPL)")
    cik: str = Field(..., description="10-digit zero-padded SEC CIK")
    company_name: str = Field(..., description="Official corporate name")
    metric_name: str = Field(
        ..., description="Standard metric code (e.g. gross_profit_margin)"
    )
    calculated_value: float | None = Field(
        None, description="Computed numerical result, or None if unavailable/invalid"
    )
    unit: str = Field(
        ..., description="Result presentation unit (e.g. 'percentage', 'ratio', 'USD')"
    )
    period_type: str = Field(
        ..., description="Temporal scope ('annual' or 'quarterly')"
    )
    period_start: str | None = Field(
        None, description="Start of calculation period (YYYY-MM-DD)"
    )
    period_end: str = Field(..., description="End of calculation period (YYYY-MM-DD)")
    fiscal_year: int | None = Field(None, description="Reporting fiscal year")
    fiscal_period: str | None = Field(
        None, description="Reporting fiscal period (FY, Q1, Q2, Q3, Q4)"
    )
    formula_name: str = Field(..., description="Canonical formula title")
    formula_expression: str = Field(
        ..., description="Exact mathematical expression used"
    )
    status: CalculationStatus = Field(..., description="Calculation outcome status")
    unavailable_reason: str | None = Field(
        None, description="Explanatory rationale if metric is unavailable or invalid"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings or nuances"
    )
    inputs: list[CalculationInputObservation] = Field(
        default_factory=list,
        description="List of source observations used in the computation",
    )
    calculated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp of when calculation was executed",
    )


class TriggerCalculationRequest(BaseModel):
    """Request payload to trigger financial calculations for a company."""

    start_year: int | None = Field(
        None, description="Earliest fiscal year to compute (inclusive)"
    )
    end_year: int | None = Field(
        None, description="Latest fiscal year to compute (inclusive)"
    )
    period_type: str | None = Field(
        "annual", description="Period type filter: 'annual' or 'quarterly'"
    )
    metrics: list[str] | None = Field(
        None,
        description="Optional list of specific metric keys to compute. If None, computes all supported metrics.",
    )


class CalculationSummaryResponse(BaseModel):
    """Summary of financial metric calculation execution."""

    ticker: str
    cik: str
    company_name: str
    period_type: str
    total_calculated: int
    total_unavailable: int
    total_invalid: int
    calculations: list[CalculationReceipt]
