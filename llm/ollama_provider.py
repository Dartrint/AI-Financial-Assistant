"""
llm/ollama_provider.py
Local LLM inference via Ollama.
"""

from __future__ import annotations

import logging
import os
import time

from llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaProvider(LLMProvider):
    """Local LLM via Ollama server."""

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self._model = model
        self._base_url = base_url
        self._client = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None:
            try:
                import ollama as _ollama  # type: ignore
                self._client = _ollama.Client(host=self._base_url, timeout=120)
            except ImportError:
                logger.warning("[Ollama] ollama package not installed")
                return None
            except Exception as e:
                logger.warning(f"[Ollama] Failed to create client: {e}")
                return None
        return self._client

    def is_available(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            models = client.list()
            model_names = [m.get("name", m.get("model", "")) for m in models.get("models", [])]
            # Check if our model is available (partial match)
            return any(self._model in name for name in model_names)
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        client = self._get_client()
        if client is None:
            return LLMResponse(
                text="", model=self._model, provider="ollama",
                error="Ollama client not available",
            )

        start = time.time()
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = client.chat(
                model=self._model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            )

            latency = (time.time() - start) * 1000
            text = response.get("message", {}).get("content", "")
            tokens = response.get("eval_count", 0) + response.get("prompt_eval_count", 0)

            return LLMResponse(
                text=text,
                model=self._model,
                provider="ollama",
                tokens_used=tokens,
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"[Ollama] Error: {e}")
            return LLMResponse(
                text="", model=self._model, provider="ollama",
                latency_ms=round(latency, 1), error=str(e),
            )
