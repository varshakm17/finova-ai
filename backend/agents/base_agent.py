"""Base Agent interface for Finova AI multi-agent orchestration.

Defines the contract that all specialized agents must fulfill to operate
as nodes within the LangGraph topology.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.agents.state import FinovaAgentState


class BaseFinovaAgent(ABC):
    """Abstract base class for all Finova AI specialized agents."""

    def __init__(self, agent_name: str, description: str) -> None:
        self.agent_name = agent_name
        self.description = description

    @abstractmethod
    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Execute the agent logic given the current workflow state.

        Args:
            state: The typed dictionary representing the current graph state.

        Returns:
            dict[str, Any]: State delta to update the LangGraph shared state.
        """
        pass
