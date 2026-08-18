"""
tools/base.py
Abstract Tool interface and ToolRegistry for agent tool management.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized tool execution result."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    answer_text: str = ""
    chart_data: dict | None = None
    citations: list[dict] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    error: str | None = None


class Tool(ABC):
    """Abstract base for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    @property
    def parameters_schema(self) -> dict:
        """JSON schema of accepted parameters (for LLM tool calling)."""
        return {}

    @abstractmethod
    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            params: Tool-specific parameters (from entity extraction)
            context: Shared context (dataset, retriever, llm_router, etc.)
        """
        ...


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def all_tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def select_tool(self, intent: str, entities: dict) -> Tool | None:
        """Select the best tool based on intent and entities."""
        intent_tool_map = {
            "market_data": "market_data",
            "market_and_knowledge": "market_data",
            "metric_lookup": "stock_analysis",
            "trend_analysis": "stock_analysis",
            "comparison": "stock_analysis",
            "ratio_calc": "stock_analysis",
            "ranking": "stock_analysis",
            "concept_explain": "explain_concept",
            "economic_analysis": "economic_analysis",
            "portfolio": "portfolio_metrics",
        }

        # Check if it's a concept question
        if entities.get("is_concept_question"):
            return self._tools.get("explain_concept")

        tool_name = intent_tool_map.get(intent, "stock_analysis")
        return self._tools.get(tool_name)
