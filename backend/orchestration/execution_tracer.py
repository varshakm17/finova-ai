"""Execution tracer and SQLite persistence for multi-agent workflows.

Tracks timing, status transitions, inputs, outputs, and errors for every agent
node in the LangGraph topology with microsecond precision.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from backend.agents.agent_models import AgentExecutionEvent, AgentExecutionStatus
from backend.data.storage import Database
from backend.utils.logger import get_logger

logger = get_logger("execution_tracer")


class StepTraceContext:
    """Context object passed inside trace_step to capture step outputs and metadata."""

    def __init__(
        self,
        event_id: str,
        request_id: str,
        step_index: int,
        agent_name: str,
        node_name: str,
        input_summary: str | None = None,
    ) -> None:
        self.event_id = event_id
        self.request_id = request_id
        self.step_index = step_index
        self.agent_name = agent_name
        self.node_name = node_name
        self.input_summary = input_summary
        self.output_summary: str | None = None
        self.error_message: str | None = None
        self.status = AgentExecutionStatus.SUCCESS.value
        self.start_time = datetime.now(UTC).isoformat()
        self.end_time = self.start_time
        self.duration_ms = 0.0
        self.metadata: dict[str, Any] = {}
        self._t0 = time.perf_counter()

    def set_output(
        self,
        summary: str,
        metadata: dict[str, Any] | None = None,
        status: str = AgentExecutionStatus.SUCCESS.value,
    ) -> None:
        """Record output summary, metadata, and status for this execution step."""
        self.output_summary = summary
        self.status = status
        if metadata:
            self.metadata.update(metadata)

    def record_error(self, error: Exception | str) -> None:
        """Record failure status and error details."""
        self.status = AgentExecutionStatus.FAILED.value
        self.error_message = str(error)

    def finalize(self) -> dict[str, Any]:
        """Compute final duration and produce structured event dictionary."""
        self.duration_ms = round((time.perf_counter() - self._t0) * 1000, 2)
        self.end_time = datetime.now(UTC).isoformat()
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "step_index": self.step_index,
            "agent_name": self.agent_name,
            "node_name": self.node_name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class ExecutionTracer:
    """Auditable execution tracer that coordinates SQLite persistence and logging."""

    def __init__(self, database: Database | None = None) -> None:
        self.db = database or Database()

    @contextmanager
    def trace_step(
        self,
        request_id: str,
        step_index: int,
        agent_name: str,
        node_name: str,
        input_summary: str | None = None,
    ) -> Generator[StepTraceContext, None, None]:
        """Context manager to instrument and persist an individual agent execution step."""
        event_id = str(uuid.uuid4())
        ctx = StepTraceContext(
            event_id=event_id,
            request_id=request_id,
            step_index=step_index,
            agent_name=agent_name,
            node_name=node_name,
            input_summary=input_summary,
        )
        try:
            yield ctx
        except Exception as exc:
            ctx.record_error(exc)
            raise
        finally:
            event_dict = ctx.finalize()
            try:
                self.db.save_execution_event(event_dict)
            except Exception as err:
                logger.warning("Failed to persist execution event to DB: %s", err)
            logger.info(
                "Step [%d] %s (%s) finished in %.2fms with status=%s",
                step_index,
                node_name,
                agent_name,
                ctx.duration_ms,
                ctx.status,
            )

    def to_event_model(self, event_dict: dict[str, Any]) -> AgentExecutionEvent:
        """Convert a raw dictionary trace into a typed AgentExecutionEvent."""
        return AgentExecutionEvent(**event_dict)
