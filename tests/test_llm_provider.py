"""Unit tests for LLM Provider abstraction, Mock Provider, and Ollama integration."""

from unittest.mock import MagicMock, patch

import pytest

from backend.llm import get_llm_provider
from backend.llm.llm_provider import LLMGenerationResponse, MockLLMProvider
from backend.llm.ollama_provider import OllamaProvider
from config.settings import get_settings


def test_mock_provider_default_generation() -> None:
    provider = MockLLMProvider(
        default_response="Apple reported strong gross margins [E1] [C1]."
    )
    assert provider.provider_name == "mock"
    assert provider.model_name == "mock-model"
    assert provider.health_check() is True

    resp = provider.generate(
        prompt="What were Apple margins?", system_prompt="Answer grounding"
    )
    assert isinstance(resp, LLMGenerationResponse)
    assert "[E1]" in resp.text
    assert "[C1]" in resp.text
    assert resp.tokens_generated > 0
    assert resp.prompt_tokens > 0
    assert resp.metadata["provider"] == "mock"


def test_mock_provider_custom_responses() -> None:
    responses = {
        "revenue": "Revenue grew by 10% [E1].",
        "risk": "Supply chain vulnerabilities are primary risks [E2].",
    }
    provider = MockLLMProvider(responses=responses)

    resp1 = provider.generate(prompt="Tell me about revenue growth")
    assert "Revenue grew by 10% [E1]." in resp1.text

    resp2 = provider.generate(prompt="What are the main risk factors?")
    assert "Supply chain vulnerabilities" in resp2.text

    resp3 = provider.generate(prompt="Unmatched query")
    assert "Mock synthesis" in resp3.text


def test_mock_provider_offline_simulation() -> None:
    provider = MockLLMProvider(healthy=False)
    assert provider.health_check() is False


def test_ollama_provider_health_check_success() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5:3b"}, {"name": "llama3:latest"}]
        }
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
        )
        assert provider.health_check() is True


def test_ollama_provider_health_check_failure() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
        )
        assert provider.health_check() is False


def test_ollama_provider_generation_success() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "Apple operating margin was 30.13% in FY2023 [C1].",
            "eval_count": 42,
            "prompt_eval_count": 128,
            "total_duration": 1500000000,
        }
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
        )
        resp = provider.generate(prompt="What was Apple operating margin?")

        assert "30.13%" in resp.text
        assert resp.tokens_generated == 42
        assert resp.prompt_tokens == 128
        assert resp.metadata["model"] == "qwen2.5:3b"


def test_ollama_provider_generation_api_error() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Model Error"
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
        )
        with pytest.raises(RuntimeError, match="Ollama generation failed"):
            provider.generate(prompt="Test prompt")


def test_ollama_provider_empty_prompt() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
    )
    with pytest.raises(ValueError, match="Generation prompt cannot be empty"):
        provider.generate(prompt="")


def test_ollama_provider_model_not_found() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="nonexistent:model"
        )
        with pytest.raises(RuntimeError, match="Model 'nonexistent:model' not found"):
            provider.generate(prompt="Hello")


def test_ollama_provider_is_model_available() -> None:
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5:3b"}, {"name": "llama3:latest"}]
        }
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider(
            base_url="http://127.0.0.1:11434", model_name="qwen2.5:3b"
        )
        assert provider.is_model_available("qwen2.5:3b") is True
        assert provider.is_model_available("mistral:7b") is False

        info = provider.get_model_info()
        assert info["provider"] == "ollama"
        assert info["service_online"] is True
        assert info["model_available"] is True


def test_get_llm_provider_factory() -> None:
    settings = get_settings()

    # Mock provider resolution
    mock_prov = get_llm_provider("mock", settings=settings)
    assert isinstance(mock_prov, MockLLMProvider)

    # Ollama provider resolution
    ollama_prov = get_llm_provider("ollama", settings=settings)
    assert isinstance(ollama_prov, OllamaProvider)

    # Unsupported provider raises ValueError
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_llm_provider("unsupported_vendor", settings=settings)
