"""
llm/router.py
LLM routing — tries providers in priority order with automatic fallback.
Supports task-based routing for different quality/speed requirements.
"""

from __future__ import annotations

import logging
import os

from llm.base import LLMProvider, LLMResponse, _strip_think_blocks
from llm.gemini_provider import GeminiProvider
from llm.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

DEFAULT_PRIORITY = os.getenv("LLM_PRIORITY", "groq,gemini")


class LLMRouter:
    """
    LLM router with priority-based provider selection.

    Default priority: Ollama (local) → Groq (cloud) → Gemini (cloud)
    Supports task-based routing for optimal quality/speed tradeoffs.
    """

    def __init__(self, priority: str | None = None):
        self._priority_order = (priority or DEFAULT_PRIORITY).split(",")
        self._providers: dict[str, LLMProvider] = {}
        self._init_providers()
        self._active_provider: str | None = None

    def _init_providers(self) -> None:
        """Initialize all available providers."""
        try:
            self._providers["groq"] = GroqProvider()
        except Exception as e:
            logger.warning(f"[Router] Groq init failed: {e}")

        try:
            self._providers["gemini"] = GeminiProvider()
        except Exception as e:
            logger.warning(f"[Router] Gemini init failed: {e}")

    @property
    def providers(self) -> dict[str, LLMProvider]:
        return self._providers

    @property
    def active_provider(self) -> str | None:
        return self._active_provider

    def get_provider(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        preferred_provider: str | None = None,
    ) -> LLMResponse:
        """
        Generate text using the highest-priority available provider.

        Tries each provider in priority order, falling back on failure.
        """
        # Build provider order
        if preferred_provider and preferred_provider in self._providers:
            order = [preferred_provider] + [
                p for p in self._priority_order if p != preferred_provider
            ]
        else:
            order = list(self._priority_order)

        for provider_name in order:
            provider = self._providers.get(provider_name)
            if provider is None:
                continue

            try:
                if not provider.is_available():
                    logger.debug(f"[Router] {provider_name} not available, skipping")
                    continue

                response = provider.generate(prompt, system, temperature, max_tokens)
                if response.error:
                    logger.warning(f"[Router] {provider_name} error: {response.error}")
                    continue

                response.text = _strip_think_blocks(response.text)
                self._active_provider = provider_name
                logger.info(
                    f"[Router] Used {provider_name}/{provider.model_name} "
                    f"({response.latency_ms:.0f}ms, {response.tokens_used} tokens)"
                )
                return response

            except Exception as e:
                logger.warning(f"[Router] {provider_name} failed: {e}")
                continue

        # All failed
        return LLMResponse(
            text="Không có LLM provider khả dụng. Vui lòng kiểm tra Ollama, Groq, hoặc Gemini.",
            model="none",
            provider="none",
            error="All providers failed",
        )

    def generate_for_task(
        self,
        prompt: str,
        system: str = "",
        task_type: str = "general",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Task-aware generation — routes to optimal provider by task type.

        Task types:
        - "entity_extraction": fast, local preferred (Ollama)
        - "answer_synthesis": quality, cloud preferred (Groq/Gemini)
        - "concept_explain": quality + context, cloud preferred
        - "general": use default priority
        """
        task_routing = {
            "entity_extraction": "ollama",
            "answer_synthesis": "groq",
            "concept_explain": "groq",
            "polish": "groq",
            "general": None,
        }

        preferred = task_routing.get(task_type)
        return self.generate(prompt, system, temperature, max_tokens, preferred)

    def status(self) -> dict:
        """Return status of all providers."""
        result = {
            "priority": self._priority_order,
            "active": self._active_provider,
            "providers": {},
        }
        for name, provider in self._providers.items():
            try:
                available = provider.is_available()
                result["providers"][name] = {
                    "available": available,
                    "model": provider.model_name,
                }
            except Exception as e:
                result["providers"][name] = {
                    "available": False,
                    "error": str(e)[:100],
                }
        return result
