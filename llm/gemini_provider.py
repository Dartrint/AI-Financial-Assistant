"""
llm/gemini_provider.py
Google Gemini cloud LLM inference.
"""

from __future__ import annotations

import logging
import os
import time

from llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # Read env at init time (after load_dotenv in app.py)
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=self._api_key)
                self._client = genai.GenerativeModel(self._model)
            except ImportError:
                logger.warning("[Gemini] google-generativeai not installed")
            except Exception as e:
                logger.warning(f"[Gemini] Failed to configure: {e}")
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
                text="", model=self._model, provider="gemini",
                error="Gemini client not available",
            )

        start = time.time()
        try:
            full_prompt = f"{system}\n\n{prompt}" if system else prompt

            response = client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )

            latency = (time.time() - start) * 1000
            text = response.text.strip() if response.text else ""

            return LLMResponse(
                text=text,
                model=self._model,
                provider="gemini",
                tokens_used=0,
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"[Gemini] Error: {e}")
            return LLMResponse(
                text="", model=self._model, provider="gemini",
                latency_ms=round(latency, 1), error=str(e),
            )