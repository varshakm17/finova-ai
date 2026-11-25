"""Data models and enums for Finova multi-agent orchestration.

Defines schemas for intent classification, workflow types, execution tracing,
and API request/response structures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentIntent(str, Enum):
    """User inquiry classifications handled by Finova supervisor."""

    GENERAL_RESEARCH = "GENERAL_RESEARCH"
    FINANCIAL_ANALYSIS = "FINANCIAL_ANALYSIS"
    COMBINED_ANALYSIS = "COMBINED_ANALYSIS"
    COMPARATIVE_RESEARCH = "COMPARATIVE_RESEARCH"
    REPORT_GENERATION = "REPORT_GENERATION"
    UNSUPPORTED_OR_AMBIGUOUS = "UNSUPPORTED_OR_AMBIGUOUS"


class AgentWorkflowType(str, Enum):
    """Workflow execution topologies selected by the supervisor."""

    RESEARCH_ONLY = "research_only"
    FINANCIAL_ONLY = "financial_only"
    COMBINED_ANALYSIS = "combined_analysis"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    FINANCIAL_RESEARCH_REPORT = "financial_research_report"
    SAFE_REJECTION = "safe_rejection"


class AgentExecutionStatus(str, Enum):
    """Execution status for individual agent nodes in the LangGraph graph."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(str, Enum):
    """Overall status of an end-to-end agent workflow execution."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class AgentExecutionEvent(BaseModel):
    """Auditable log entry for an individual agent/node execution step."""

    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    step_index: int = 0
    agent_name: str
    node_name: str
    status: str = AgentExecutionStatus.SUCCESS.value
    start_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    end_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float = 0.0
    input_summary: str | None = None
    output_summary: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    """Full execution run metadata with trace events."""

    model_config = ConfigDict(extra="ignore")

    request_id: str
    user_question: str
    company_ticker: str | None = None
    intent: str = AgentIntent.GENERAL_RESEARCH.value
    workflow_type: str = AgentWorkflowType.RESEARCH_ONLY.value
    status: str = WorkflowStatus.PENDING.value
    final_answer: str | None = None
    verification_status: str | None = None
    retrieved_evidence_count: int = 0
    calculation_receipts_count: int = 0
    total_duration_ms: float = 0.0
    error_message: str | None = None
    trace_events: list[AgentExecutionEvent] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AgentRunRequest(BaseModel):
    """Request payload for running a multi-agent orchestrated research query."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Financial inquiry or research question",
        examples=["What were Apple's primary revenue drivers in fiscal year 2023?"],
    )
    company_ticker: str | None = Field(
        default=None,
        description="Stock ticker symbol if targeting a specific company (e.g. AAPL, MSFT)",
        examples=["AAPL"],
    )
    reporting_period: str | None = Field(
        default=None,
        description="Target reporting period (e.g. FY2023, 2023, Q3)",
        examples=["FY2023"],
    )
    max_steps: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum execution steps before terminating graph",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Maximum total execution time allowed in seconds",
    )
    mock_llm_response: str | None = Field(
        default=None,
        description="Optional pre-determined LLM response for deterministic testing",
    )


class AgentRunResponse(BaseModel):
    """Response payload returned from multi-agent orchestration."""

    model_config = ConfigDict(extra="ignore")

    request_id: str
    question: str
    company_ticker: str | None = None
    intent: str
    workflow_type: str
    status: str
    final_answer: str | None = None
    verification_status: str | None = None
    retrieved_evidence_count: int = 0
    calculation_receipts_count: int = 0
    total_duration_ms: float = 0.0
    trace: list[AgentExecutionEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# Session 11: Autonomous Research Planning, Tasks & Report Models
# =============================================================================


class TaskType(str, Enum):
    """Categorization of individual autonomous research tasks."""

    FILING_RETRIEVAL = "filing_retrieval"
    FINANCIAL_METRIC_EXTRACTION = "financial_metric_extraction"
    METRIC_CALCULATION = "metric_calculation"
    TREND_ANALYSIS = "trend_analysis"
    MDA_ANALYSIS = "mda_analysis"
    RISK_ANALYSIS = "risk_analysis"
    SYNTHESIS = "synthesis"
    VERIFICATION = "verification"


class TaskStatus(str, Enum):
    """Execution status for individual research tasks."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class ResearchTask(BaseModel):
    """Individual atomic research activity within a structured research plan."""

    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: TaskType
    title: str
    description: str
    target_sections: list[str] = Field(default_factory=list)
    target_metrics: list[str] = Field(default_factory=list)
    target_periods: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)


class ReportSectionPlan(BaseModel):
    """Outlined plan for an individual report section."""

    model_config = ConfigDict(extra="ignore")

    section_key: str
    title: str
    order_index: int
    required_data_sources: list[str] = Field(default_factory=list)
    description: str = ""


class ResearchPlan(BaseModel):
    """Autonomous research plan decomposing a user objective into actionable tasks."""

    model_config = ConfigDict(extra="ignore")

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str = "Target Company"
    ticker: str | None = None
    cik: str | None = None
    objective: str = ""
    reporting_period: str | None = None
    fiscal_years: list[int] = Field(default_factory=list)
    target_periods: list[str] = Field(default_factory=list)
    required_filing_types: list[str] = Field(default_factory=lambda: ["10-K"])
    required_metrics: list[str] = Field(default_factory=list)
    narrative_topics: list[str] = Field(default_factory=list)
    expected_sections: list[ReportSectionPlan] = Field(default_factory=list)
    tasks: list[ResearchTask] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    is_valid: bool = True
    planning_method: str = "deterministic"
    planning_rationale: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ResearchPlanValidation(BaseModel):
    """Validation audit for a research plan."""

    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchTaskResult(BaseModel):
    """Outcome and retrieved evidence from executing an individual research task."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    question: str
    execution_status: TaskStatus = TaskStatus.COMPLETED
    retrieved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    filing_refs: list[str] = Field(default_factory=list)
    reporting_periods: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FinancialTrend(BaseModel):
    """Deterministic longitudinal metric direction and magnitude."""

    model_config = ConfigDict(extra="ignore")

    metric_name: str
    periods: list[str]
    values: list[float]
    unit: str
    direction: str  # "UPWARD", "DOWNWARD", "FLAT", "MIXED"
    absolute_change: float
    percentage_change: float | None = None
    supporting_receipt_ids: list[str] = Field(default_factory=list)
    interpretation_notes: str = ""


class MetricComparison(BaseModel):
    """Period-over-period financial metric comparison."""

    metric_name: str
    base_period: str
    base_value: float
    comparison_period: str
    comparison_value: float
    absolute_delta: float
    percentage_delta: float | None = None
    unit: str


class FinancialAnalysisResult(BaseModel):
    """Consolidated financial analysis container across requested fiscal periods."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    company_name: str
    period_type: str = "annual"
    periods_analyzed: list[str] = Field(default_factory=list)
    trends: list[FinancialTrend] = Field(default_factory=list)
    comparisons: list[MetricComparison] = Field(default_factory=list)
    calculation_receipts: list[dict[str, Any]] = Field(default_factory=list)
    missing_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportTable(BaseModel):
    """Structured markdown and HTML table representation."""

    title: str
    headers: list[str]
    rows: list[list[str]]


class ReportSection(BaseModel):
    """Content and evidence links for a single section of a research brief."""

    model_config = ConfigDict(extra="ignore")

    section_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    section_key: str
    title: str
    order_index: int = 0
    content_markdown: str
    evidence_ids: list[str] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    tables: list[ReportTable] = Field(default_factory=list)
    verification_status: str = "UNVERIFIED"


class ReportReference(BaseModel):
    """Auditable citation pointing to statutory SEC filing disclosures."""

    model_config = ConfigDict(extra="ignore")

    reference_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ref_type: str  # "filing_passage" or "calculation_receipt"
    citation_id: str  # "E1", "C1", etc.
    filing_name: str | None = None
    form_type: str | None = None
    filing_date: str | None = None
    reporting_period: str | None = None
    accession_number: str | None = None
    sec_url: str | None = None
    description: str | None = None


class ReportMetadata(BaseModel):
    """Administrative and provenance metadata for a generated report."""

    model_config = ConfigDict(extra="ignore")

    report_id: str
    request_id: str
    plan_id: str | None = None
    company_name: str
    ticker: str | None = None
    title: str
    reporting_period: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str = "1.0.0"
    verification_status: str = "UNVERIFIED"


class FinancialResearchReport(BaseModel):
    """Top-level container for an autonomous multi-section financial research brief."""

    model_config = ConfigDict(extra="ignore")

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    plan_id: str | None = None
    ticker: str | None = None
    company_name: str
    title: str
    reporting_period: str | None = None
    status: str = WorkflowStatus.COMPLETED.value
    verification_status: str = "UNVERIFIED"
    executive_summary: str | None = None
    markdown_content: str
    html_content: str | None = None
    sections: list[ReportSection] = Field(default_factory=list)
    references: list[ReportReference] = Field(default_factory=list)
    total_evidence_cited: int = 0
    total_calculations_cited: int = 0
    metadata: ReportMetadata | None = None
    warnings: list[str] = Field(default_factory=list)


class ReportGenerationRequest(BaseModel):
    """Request payload for generating an autonomous financial research report."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Research brief request or objective",
        examples=[
            "Analyze Microsoft's financial performance over the last three fiscal years, including revenue growth, profitability, cash flow, and major business risks."
        ],
    )
    ticker: str | None = Field(
        default=None, description="Target company ticker (e.g. MSFT, AAPL)"
    )
    company_name: str | None = Field(
        default=None, description="Target company official title"
    )
    reporting_period: str | None = Field(
        default=None, description="Filing reporting period (e.g. FY2023, 2021-2023)"
    )
    output_format: str = Field(
        default="markdown",
        description="Output format: 'markdown' or 'html'",
    )
    max_steps: int = Field(default=20, ge=5, le=50)
    timeout_seconds: float = Field(default=120.0, ge=10.0, le=300.0)
    mock_llm_response: str | None = Field(
        default=None, description="Optional deterministic mock text for testing"
    )


class ReportGenerationResponse(BaseModel):
    """Response payload returned from autonomous report generation."""

    model_config = ConfigDict(extra="ignore")

    request_id: str
    report_id: str
    status: str
    verification_status: str
    plan_summary: str
    report: FinancialResearchReport | None = None
    markdown_content: str | None = None
    html_content: str | None = None
    total_sections: int = 0
    total_evidence_cited: int = 0
    total_calculations_cited: int = 0
    execution_time_ms: float = 0.0
    trace: list[AgentExecutionEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
