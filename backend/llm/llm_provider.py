"""LLM Provider abstraction layer for Finova AI.

Defines a vendor-agnostic interface for local and remote Large Language Models,
enforcing deterministic responses, standardized generation metadata, and health auditing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("llm_provider")


class LLMGenerationResponse(BaseModel):
    """Standardized response container returned by any LLM provider."""

    text: str = Field(..., description="Generated text completion from the model")
    model: str = Field(..., description="Active model identifier")
    provider: str = Field(
        ..., description="Underlying provider identifier (e.g. 'ollama', 'mock')"
    )
    prompt_tokens: int | None = Field(
        default=None, description="Number of tokens in the input prompt"
    )
    completion_tokens: int | None = Field(
        default=None,
        description="Number of tokens generated in completion",
    )
    total_duration_ms: float | None = Field(
        default=None,
        description="Total roundtrip request duration in milliseconds",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific execution metadata",
    )

    @property
    def tokens_generated(self) -> int:
        """Alias for completion_tokens or word count fallback."""
        if self.completion_tokens is not None:
            return self.completion_tokens
        return len(self.text.split())

    @property
    def total_tokens(self) -> int:
        """Aggregate total of prompt tokens and generated completion tokens."""
        return (self.prompt_tokens or 0) + self.tokens_generated


class LLMProvider(ABC):
    """Abstract base class defining the standard interface for LLM backends."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique name of this provider implementation."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the active model name or identifier."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMGenerationResponse:
        """Generate a completion for the given prompt.

        Args:
            prompt: User/context prompt text.
            system_prompt: Optional system instruction prompt.
            max_tokens: Optional maximum completion tokens cutoff.
            temperature: Optional sampling temperature.

        Returns:
            LLMGenerationResponse with generated text and metadata.

        Raises:
            RuntimeError: If the model service is unavailable or generation fails.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check whether the underlying provider service is reachable and functional."""
        ...

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """Return diagnostic metadata about the configured model and provider."""
        ...


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for offline unit and integration testing."""

    def __init__(
        self,
        canned_response: str | None = None,
        default_response: str | None = None,
        responses: dict[str, str] | None = None,
        is_healthy: bool = True,
        healthy: bool | None = None,
        model_name: str = "mock-model",
        settings: Settings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self.canned_response = (
            default_response
            or canned_response
            or "Mock synthesis response: Apple reported strong gross margins [E1] [C1]."
        )
        self.responses = responses or {}
        if healthy is not None:
            self._is_healthy = healthy
        else:
            self._is_healthy = is_healthy
        self._model_name = model_name
        self.generation_history: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMGenerationResponse:
        if not self._is_healthy:
            raise RuntimeError("Mock LLM service is offline or unreachable.")

        selected_text = self.canned_response
        p_lower = prompt.lower()
        for kw, resp in self.responses.items():
            if kw.lower() in p_lower:
                selected_text = resp
                break

        self.generation_history.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )

        return LLMGenerationResponse(
            text=selected_text,
            model=self.model_name,
            provider=self.provider_name,
            prompt_tokens=max(1, len(prompt.split())),
            completion_tokens=max(1, len(selected_text.split())),
            total_duration_ms=15.0,
            metadata={"mock": True, "provider": self.provider_name},
        )

    def health_check(self) -> bool:
        return self._is_healthy

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "status": "healthy" if self._is_healthy else "unhealthy",
            "is_mock": True,
        }
