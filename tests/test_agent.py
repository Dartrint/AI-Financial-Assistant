import os
import unittest
from unittest.mock import patch

import pandas as pd

from agent import FinancialAgent, classify_intent
from tools.base import ToolRegistry
from tools.market_data import MarketDataTool


class FakeAggregator:
    def fetch_market_info(self, ticker: str) -> dict:
        return {
            "current_price": 125_000,
            "pe_ratio": 18.5,
            "pb_ratio": 3.2,
            "currency": "VND",
        }

    def fetch_macro(self, indicator: str) -> dict:
        return {"value": 3.2, "unit": "%", "period": "2026-07", "source": "EcoData"}


class TestFinancialAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = pd.DataFrame(
            {
                "company_code": ["VCB"],
                "year": [2024],
                "line_item_normalized": ["doanh_thu_thuan"],
                "value": [100],
                "source_page": ["demo"],
            }
        )

    def test_uses_qroq_env_when_present(self) -> None:
        with patch.dict(
            os.environ,
            {"QROQ_API_KEY": "demo-key", "QROQ_MODEL": "qroq-test", "QROQ_BASE_URL": "https://example.test/v1"},
            clear=False,
        ):
            agent = FinancialAgent(self.dataset)
            self.assertTrue(agent.llm_enabled)
            self.assertEqual(agent.api_key, "demo-key")
            self.assertEqual(agent.model, "qroq-test")
            self.assertEqual(agent.base_url, "https://example.test/v1")

    def test_falls_back_without_qroq_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            agent = FinancialAgent(self.dataset)
            self.assertFalse(agent.llm_enabled)

    def test_live_questions_are_not_routed_to_annual_statement_tool(self) -> None:
        self.assertEqual(classify_intent("P/E của FPT hiện tại là bao nhiêu?"), "market_data")
        self.assertEqual(classify_intent("P/E của FPT hiện tại cao hay thấp?"), "market_and_knowledge")
        self.assertEqual(classify_intent("Sharpe Ratio là gì?"), "concept_explain")
        self.assertEqual(classify_intent("CPI được tính như thế nào?"), "concept_explain")
        self.assertEqual(classify_intent("CAPM hoạt động ra sao?"), "concept_explain")

    def test_market_answer_has_source_citation(self) -> None:
        registry = ToolRegistry()
        registry.register(MarketDataTool())
        agent = FinancialAgent(
            self.dataset,
            tool_registry=registry,
            aggregator=FakeAggregator(),
        )
        result = agent.answer("P/E của FPT hiện tại là bao nhiêu?")
        self.assertEqual(result["tool_used"], "market_data")
        self.assertIn("18.50x", result["answer"])
        self.assertEqual(result["citations"][0]["source"], "Yahoo Finance")

    def test_macro_answer_uses_market_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(MarketDataTool())
        agent = FinancialAgent(self.dataset, tool_registry=registry, aggregator=FakeAggregator())
        result = agent.answer("CPI Việt Nam hiện tại?")
        self.assertEqual(result["tool_used"], "market_data")
        self.assertIn("3.2", result["answer"])


if __name__ == "__main__":
    unittest.main()
