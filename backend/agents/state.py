"""Shared state definition for Finova LangGraph multi-agent workflows.

Provides a strongly-typed TypedDict schema with list-append reducers for
trace logging, warnings, and errors across asynchronous and synchronous graph nodes.
"""

from __future__ import annotations

from typing import Any

from typing_extensions import Annotated, TypedDict


def append_list(a: list[Any] | None, b: list[Any] | Any | None) -> list[Any]:
    """Reducer function to append elements or lists without overwriting previous state."""
    res = list(a) if a is not None else []
    if b is None:
        return res
    if isinstance(b, list):
        return res + b
    return res + [b]


class FinovaAgentState(TypedDict, total=False):
    """Strongly-typed shared state passed between Finova agent nodes."""

    # Core request metadata
    request_id: str
    user_question: str
    company_ticker: str | None
    company_name: str | None
    reporting_period: str | None

    # Intent and workflow routing
    intent: str | None
    workflow_type: str | None
    selected_agents: list[str]
    research_query: str | None

    # Intermediate evidence & calculations
    retrieved_evidence: list[dict[str, Any]]
    calculation_results: list[dict[str, Any]]

    # Session 11: Autonomous Research Planning, Consolidation & Reports
    research_plan: dict[str, Any] | None
    task_results: list[dict[str, Any]]
    financial_analysis: dict[str, Any] | None
    consolidated_findings: dict[str, Any] | None
    generated_report: dict[str, Any] | None
    report_markdown: str | None
    report_html: str | None
    report_verification: dict[str, Any] | None
    output_format: str | None

    # Synthesis & Verification
    generated_answer: str | None
    verification_result: dict[str, Any] | None
    final_answer: str | None

    # Audit & Monitoring (with append reducers)
    execution_trace: Annotated[list[dict[str, Any]], append_list]
    errors: Annotated[list[str], append_list]
    warnings: Annotated[list[str], append_list]

    # Graph Execution Control
    current_step: str | None
    status: str
    step_count: int
    retry_count: int
    mock_llm_response: str | None
    metadata: dict[str, Any]
