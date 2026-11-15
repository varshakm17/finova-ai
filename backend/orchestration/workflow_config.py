"""Workflow execution configuration and safety limits for Finova AI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowConfig:
    """Configurable boundaries and safety limits for multi-agent graph execution."""

    max_steps: int = 15
    timeout_seconds: float = 60.0
    max_retries: int = 2
    strict_verification: bool = True
    top_k_evidence: int = 5
    allow_mock_llm: bool = True
    require_citations: bool = True
    min_confidence_score: float = 0.5
    default_llm_model: str = "llama3:8b"
    extra_settings: dict[str, str] = field(default_factory=dict)
