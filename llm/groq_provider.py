"""
llm/groq_provider.py
Groq cloud LLM inference.
"""

from __future__ import annotations

import logging
import os
import time

from llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# GROQ_* is the supported spelling. QROQ_* is retained for existing .env files
# created by the first prototype.
DEFAULT_MODEL = os.getenv("GROQ_MODEL") or os.getenv("QROQ_MODEL", "qwen/qwen3.6-27b")
API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("QROQ_API_KEY", "")


class GroqProvider(LLMProvider):
    """Groq cloud LLM provider."""

    def __init__(self, api_key: str = API_KEY, model: str = DEFAULT_MODEL):
        self._api_key = api_key
        self._model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                from groq import Groq  # type: ignore
                self._client = Groq(api_key=self._api_key)
            except ImportError:
                logger.warning("[Groq] groq package not installed")
            except Exception as e:
                logger.warning(f"[Groq] Failed to create client: {e}")
        return self._client

    def is_available(self) -> bool:
        return bool(self._api_key) and self._get_client() is not None

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
                text="", model=self._model, provider="groq",
                error="Groq client not available",
            )

        start = time.time()
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            latency = (time.time() - start) * 1000
            text = response.choices[0].message.content.strip()
            tokens = getattr(response.usage, "total_tokens", 0)

            return LLMResponse(
                text=text,
                model=self._model,
                provider="groq",
                tokens_used=tokens,
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"[Groq] Error: {e}")
            return LLMResponse(
                text="", model=self._model, provider="groq",
                latency_ms=round(latency, 1), error=str(e),
            )
