"""
llm/base.py
Abstract interface for LLM providers.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


_THINK_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from model output."""
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    return cleaned.strip()


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    model: str
    provider: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    def health_check(self) -> dict:
        """Quick health check."""
        start = time.time()
        try:
            if not self.is_available():
                return {"available": False, "provider": self.provider_name, "error": "Not available"}
            resp = self.generate("Say 'OK'", max_tokens=10)
            latency = (time.time() - start) * 1000
            return {
                "available": True,
                "provider": self.provider_name,
                "model": self.model_name,
                "latency_ms": round(latency, 1),
                "response": resp.text[:50],
            }
        except Exception as e:
            return {"available": False, "provider": self.provider_name, "error": str(e)[:100]}
