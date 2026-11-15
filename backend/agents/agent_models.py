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
    UNSUPPORTED_OR_AMBIGUOUS = "UNSUPPORTED_OR_AMBIGUOUS"


class AgentWorkflowType(str, Enum):
    """Workflow execution topologies selected by the supervisor."""

    RESEARCH_ONLY = "research_only"
    FINANCIAL_ONLY = "financial_only"
    COMBINED_ANALYSIS = "combined_analysis"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
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
