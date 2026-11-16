"""Evaluation and Benchmark Pydantic Data Models for Finova AI.

Defines schemas for evaluation runs, per-case outcomes, aggregated benchmark metrics,
diagnostic issues, and runner payloads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationType(str, Enum):
    """Supported evaluation categories."""

    ALL = "all"
    RETRIEVAL = "retrieval"
    FINANCIAL_CALCULATION = "financial_calculation"
    VERIFICATION = "verification"
    REPORT = "report"


class EvaluationStatus(str, Enum):
    """Execution status of an evaluation benchmark run."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationIssueSeverity(str, Enum):
    """Severity classification for benchmark diagnostic issues."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvaluationIssue(BaseModel):
    """Diagnostic issue or failure recorded during a benchmark evaluation."""

    model_config = ConfigDict(extra="ignore")

    issue_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    case_id: str | None = None
    issue_type: str  # "retrieval_miss", "calc_mismatch", "false_acceptance", "false_rejection", etc.
    severity: EvaluationIssueSeverity | str = EvaluationIssueSeverity.MEDIUM
    description: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class EvaluationMetric(BaseModel):
    """Computed metric item (e.g. MAP, Precision@5, MAE, FAR)."""

    model_config = ConfigDict(extra="ignore")

    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    eval_type: str
    metric_name: str
    metric_value: float
    metric_category: str = "macro"  # "macro", "micro", "slice"
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationCaseResult(BaseModel):
    """Outcome and diagnostics for an individual test case in a benchmark dataset."""

    model_config = ConfigDict(extra="ignore")

    case_result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    case_id: str
    eval_type: str
    passed: bool = True
    metrics: dict[str, Any] = Field(default_factory=dict)
    input_summary: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None
    error_message: str | None = None
    provenance: str = "synthetic_fixture"  # "verified_sec_xbrl_inputs", "manually_annotated_sec_filing", "synthetic_fixture"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class EvaluationSummary(BaseModel):
    """High-level summary of an evaluation run."""

    model_config = ConfigDict(extra="ignore")

    eval_type: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    key_findings: list[str] = Field(default_factory=list)


class EvaluationRun(BaseModel):
    """Comprehensive record of an evaluation benchmark execution."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    eval_type: str = EvaluationType.ALL.value
    dataset_name: str = "standard_benchmark"
    dataset_version: str = "1.0.0"
    software_version: str = "1.0.0"
    commit_sha: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = EvaluationStatus.COMPLETED.value
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    duration_ms: float = 0.0
    summary: EvaluationSummary | dict[str, Any] = Field(default_factory=dict)
    metrics: list[EvaluationMetric] = Field(default_factory=list)
    issues: list[EvaluationIssue] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class EvaluationRunRequest(BaseModel):
    """Request payload for triggering an evaluation run via REST API or CLI."""

    eval_type: str = Field(
        default=EvaluationType.ALL.value,
        description="Evaluation scope: 'all', 'retrieval', 'financial_calculation', 'verification', or 'report'",
    )
    dataset_path: str | None = Field(
        default=None,
        description="Optional custom path to a benchmark dataset file",
    )
    top_k: int = Field(
        default=5, ge=1, le=50, description="Top-K cut-off for ranking metrics"
    )
    retrieval_mode: str | None = Field(
        default=None,
        description="Optional retrieval mode override ('dense', 'sparse', 'hybrid', 'reranked')",
    )
    save_results: bool = Field(
        default=True, description="Whether to persist results to SQLite database"
    )


class BenchmarkDatasetMeta(BaseModel):
    """Provenance and metadata describing an evaluation benchmark dataset."""

    name: str
    benchmark_type: str
    version: str
    total_cases: int
    companies: list[str] = Field(default_factory=list)
    provenance_breakdown: dict[str, int] = Field(default_factory=dict)
    description: str
