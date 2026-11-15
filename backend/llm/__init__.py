"""LLM Provider package for Finova AI."""

from backend.llm.llm_provider import (
    LLMGenerationResponse,
    LLMProvider,
    MockLLMProvider,
)
from backend.llm.ollama_provider import OllamaProvider
from config.settings import Settings, get_settings


def get_llm_provider(
    provider_type: str | None = None,
    settings: Settings | None = None,
) -> LLMProvider:
    """Factory creating configured LLM provider instance.

    Args:
        provider_type: Optional provider identifier override ('mock' or 'ollama').
        settings: Optional application settings.

    Returns:
        Configured LLMProvider instance.
    """
    app_settings = settings or get_settings()
    ptype = (provider_type or app_settings.LLM_PROVIDER).lower().strip()

    if ptype == "mock":
        return MockLLMProvider(settings=app_settings)
    elif ptype == "ollama":
        return OllamaProvider(settings=app_settings)
    else:
        raise ValueError(
            f"Unsupported LLM provider: '{ptype}'. Supported: 'mock', 'ollama'."
        )


__all__ = [
    "LLMGenerationResponse",
    "LLMProvider",
    "MockLLMProvider",
    "OllamaProvider",
    "get_llm_provider",
]
