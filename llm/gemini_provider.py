"""
llm/gemini_provider.py
Google Gemini cloud LLM inference — uses google-genai SDK (v1+).
Falls back to legacy google-generativeai if new SDK not installed.
"""

from __future__ import annotations

import logging
import os
import time

from llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider (google-genai SDK)."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self._client = None
        self._use_legacy = False  # will be set in _get_client

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        if self._client is None and self._api_key:
            # Try new google-genai SDK first
            try:
                from google import genai  # type: ignore
                self._client = genai.Client(api_key=self._api_key)
                self._use_legacy = False
                logger.info("[Gemini] Using google-genai SDK")
                return self._client
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"[Gemini] google-genai init failed: {e}")

            # Fallback: legacy google-generativeai
            try:
                import google.generativeai as genai_legacy  # type: ignore
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    genai_legacy.configure(api_key=self._api_key)
                    self._client = genai_legacy.GenerativeModel(self._model)
                self._use_legacy = True
                logger.info("[Gemini] Using legacy google-generativeai SDK")
            except ImportError:
                logger.warning("[Gemini] Neither google-genai nor google-generativeai installed")
            except Exception as e:
                logger.warning(f"[Gemini] Legacy init failed: {e}")

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
            if self._use_legacy:
                # Legacy google-generativeai path
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
            else:
                # New google-genai SDK path
                from google.genai import types  # type: ignore
                contents = []
                if system:
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(text=system)],
                    ))
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                ))
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
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