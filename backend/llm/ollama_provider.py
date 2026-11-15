"""Local Ollama LLM provider implementation for Finova AI.

Interfaces with a locally running Ollama instance over HTTP, supporting
CPU-friendly quantized instruction models (e.g. qwen2.5:3b, llama3.2:3b).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from backend.llm.llm_provider import LLMGenerationResponse, LLMProvider
from backend.utils.logger import get_logger
from config.settings import Settings

logger = get_logger("ollama_provider")


class OllamaProvider(LLMProvider):
    """Local LLM provider interfacing with an Ollama HTTP daemon."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(settings=settings)
        cfg_base = getattr(self.settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        cfg_model = getattr(self.settings, "OLLAMA_MODEL", "qwen2.5:3b")
        self.base_url = (base_url or cfg_base).rstrip("/")
        self.active_model = model_name or cfg_model
        timeout = getattr(self.settings, "LLM_REQUEST_TIMEOUT", 30.0)
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.active_model

    def health_check(self) -> bool:
        """Verify that Ollama daemon is running and reachable."""
        try:
            resp = self._client.get(f"{self.base_url}/api/version", timeout=2.5)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=2.5)
            return resp.status_code == 200
        except Exception:
            return False

    def is_model_available(self, model_name: str | None = None) -> bool:
        """Check if the requested model is pulled and available in local Ollama."""
        target_model = model_name or self.active_model
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=3.5)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("models", [])
            for m in models:
                name = m.get("name", "")
                if name == target_model or name.startswith(f"{target_model}:"):
                    return True
            return False
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMGenerationResponse:
        """Submit prompt to Ollama's /api/generate endpoint.

        Args:
            prompt: Context-assembled user prompt.
            system_prompt: System behavioral and grounding instructions.
            max_tokens: Maximum tokens to generate (num_predict).
            temperature: Sampling temperature.

        Returns:
            LLMGenerationResponse containing the generated answer text.

        Raises:
            RuntimeError: If Ollama service is unreachable, timed out, or returns an error.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Generation prompt cannot be empty or whitespace-only.")

        num_predict = max_tokens or self.settings.LLM_MAX_TOKENS
        temp = temperature if temperature is not None else self.settings.LLM_TEMPERATURE
        num_ctx = self.settings.LLM_CONTEXT_WINDOW

        payload: dict[str, Any] = {
            "model": self.active_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temp,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        url = f"{self.base_url}/api/generate"
        start_time = time.perf_counter()

        logger.info(
            "Submitting generation request to Ollama [model=%s, temp=%.2f, max_tokens=%d]...",
            self.active_model,
            temp,
            num_predict,
        )

        try:
            resp = self._client.post(
                url, json=payload, timeout=self.settings.LLM_REQUEST_TIMEOUT
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if resp.status_code == 404:
                raise RuntimeError(
                    f"Model '{self.active_model}' not found in local Ollama. "
                    f"Please pull the model using: ollama pull {self.active_model}"
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama generation failed with HTTP status {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            generated_text = data.get("response", "")
            prompt_tokens = data.get("prompt_eval_count")
            completion_tokens = data.get("eval_count")

            logger.info(
                "Ollama generation succeeded in %.1fms (prompt_tokens=%s, completion_tokens=%s).",
                elapsed_ms,
                prompt_tokens,
                completion_tokens,
            )

            return LLMGenerationResponse(
                text=generated_text,
                model=self.active_model,
                provider=self.provider_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_duration_ms=round(elapsed_ms, 2),
                metadata={
                    "model": self.active_model,
                    "total_duration_ns": data.get("total_duration"),
                    "load_duration_ns": data.get("load_duration"),
                    "eval_duration_ns": data.get("eval_duration"),
                },
            )

        except httpx.ConnectError as exc:
            logger.warning(
                "Failed to connect to local Ollama service at %s: %s",
                self.base_url,
                exc,
            )
            raise RuntimeError(
                f"Local Ollama service is unreachable at {self.base_url}. "
                "Ensure Ollama is running ('ollama serve')."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.warning(
                "Ollama generation timed out after %.1fs: %s",
                self.settings.LLM_REQUEST_TIMEOUT,
                exc,
            )
            raise RuntimeError(
                f"Ollama generation timed out after {self.settings.LLM_REQUEST_TIMEOUT}s."
            ) from exc
        except Exception as exc:
            if isinstance(exc, (ValueError, RuntimeError)):
                raise
            logger.error("Unexpected error communicating with Ollama: %s", exc)
            raise RuntimeError(f"Ollama generation communication error: {exc}") from exc

    def get_model_info(self) -> dict[str, Any]:
        """Return diagnostic operational info for Ollama."""
        is_healthy = self.health_check()
        model_pulled = self.is_model_available() if is_healthy else False

        return {
            "provider": self.provider_name,
            "model": self.active_model,
            "base_url": self.base_url,
            "service_online": is_healthy,
            "model_available": model_pulled,
            "context_window": self.settings.LLM_CONTEXT_WINDOW,
            "temperature": self.settings.LLM_TEMPERATURE,
            "max_tokens": self.settings.LLM_MAX_TOKENS,
        }
