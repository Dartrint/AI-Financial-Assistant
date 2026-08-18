"""
agent.py
Multi-layer Financial Agent — Orchestrator.

Architecture:
  Market Data Layer → Knowledge Layer → Retrieval Layer → LLM Layer → Tools Layer

Pipeline:
  1. Intent Classifier (local regex)
  2. Entity Extractor (LLM or regex fallback)
  3. Tool Selection (based on intent)
  4. Tool Execution (data retrieval + computation)
  5. Knowledge Retrieval (RAG for context)
  6. Answer Synthesis (LLM polish)
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import textwrap
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

from config import (
    COMPANY_ALIASES,
    LINE_ITEM_PATTERNS,
    RATIO_DEFINITIONS,
    SUPPORTED_TICKERS,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
logger = logging.getLogger(__name__)

# Intent labels
INTENTS = {
    "market_data": "Truy vấn dữ liệu thị trường hoặc vĩ mô mới nhất",
    "market_and_knowledge": "Kết hợp dữ liệu mới nhất với kiến thức nền tảng",
    "metric_lookup": "Tra cứu giá trị đơn lẻ",
    "trend_analysis": "Phân tích xu hướng nhiều năm",
    "comparison": "So sánh nhiều công ty",
    "ratio_calc": "Tính tỷ số tài chính",
    "ranking": "Xếp hạng công ty theo chỉ tiêu",
    "concept_explain": "Giải thích khái niệm tài chính",
    "economic_analysis": "Phân tích kinh tế vĩ mô",
    "portfolio": "Phân tích danh mục đầu tư",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def _normalize(text: str) -> str:
    return _strip_accents(str(text)).lower().strip()


# ---------------------------------------------------------------------------
# Step 1: Intent Classifier
# ---------------------------------------------------------------------------

_COMPARISON_KEYWORDS = [
    "so sánh", "so sanh", "so với", "so voi", "compare", "vs",
    "đối chiếu", "doi chieu",
]
_TREND_KEYWORDS = [
    "nhiều năm", "nhieu nam", "qua các năm", "xu hướng", "xu huong",
    "tăng trưởng", "tang truong", "cagr", "5 năm", "3 năm",
    "gần đây", "gan day",
]
_RATIO_KEYWORDS = [
    "roe", "roa", "tỷ lệ", "ty le", "biên lợi nhuận", "bien loi nhuan",
    "current ratio", "debt ratio", "p/e", "tỷ số", "ty so",
    "lợi nhuận trên vốn", "loi nhuan tren von",
]
_RANKING_KEYWORDS = [
    "top", "xếp hạng", "xep hang", "cao nhất", "cao nhat",
    "lớn nhất", "lon nhat", "ranking", "hạng",
]
_CONCEPT_KEYWORDS = [
    "là gì", "la gi", "giải thích", "giai thich", "explain", "what is",
    "định nghĩa", "dinh nghia", "nghĩa là", "meaning",
    "khái niệm", "khai niem", "thuật ngữ", "thuat ngu",
    "công thức", "cong thuc", "formula", "được tính", "duoc tinh",
    "cách tính", "cach tinh", "như thế nào", "nhu the nao", "how does",
    "hoạt động", "hoat dong",
]
_ECONOMIC_KEYWORDS = [
    "gdp", "lạm phát", "lam phat", "inflation", "lãi suất", "lai suat",
    "tỷ giá", "ty gia", "kinh tế vĩ mô", "kinh te vi mo", "macro",
    "chính sách tiền tệ", "chinh sach tien te", "fdi",
    "cán cân thương mại", "can can thuong mai",
]
_PORTFOLIO_KEYWORDS = [
    "danh mục", "danh muc", "portfolio", "sharpe", "correlation",
    "tương quan", "tuong quan", "đa dạng hóa", "da dang hoa",
    "diversi", "rủi ro danh mục", "rui ro danh muc",
]

# A live value must never be inferred from the RAG corpus or an annual report.
_LIVE_DATA_KEYWORDS = [
    "hiện tại", "hien tai", "mới nhất", "moi nhat", "hôm nay", "hom nay",
    "giá cổ phiếu", "gia co phieu", "thị giá", "thi gia", "market cap",
    "vốn hóa", "von hoa", "p/e", "pe ratio", "p/b", "pb ratio", "eps",
    "cpi", "gdp", "lãi suất", "lai suat", "tỷ giá", "ty gia",
]
_INTERPRETATION_KEYWORDS = [
    "cao hay thấp", "cao hay thap", "đắt hay rẻ", "dat hay re",
    "ý nghĩa", "y nghia", "đánh giá", "danh gia", "so với", "so voi",
]


def classify_intent(question: str) -> str:
    q = _normalize(question)

    if any(kw in q for kw in _CONCEPT_KEYWORDS):
        return "concept_explain"
    if any(kw in q for kw in _LIVE_DATA_KEYWORDS):
        if any(kw in q for kw in _INTERPRETATION_KEYWORDS):
            return "market_and_knowledge"
        return "market_data"
    if any(kw in q for kw in _ECONOMIC_KEYWORDS):
        return "economic_analysis"
    if any(kw in q for kw in _PORTFOLIO_KEYWORDS):
        return "portfolio"
    if any(kw in q for kw in _RANKING_KEYWORDS):
        return "ranking"
    if any(kw in q for kw in _COMPARISON_KEYWORDS):
        return "comparison"
    if any(kw in q for kw in _RATIO_KEYWORDS):
        return "ratio_calc"
    if any(kw in q for kw in _TREND_KEYWORDS):
        years_found = re.findall(r"\b20\d{2}\b", q)
        if len(years_found) >= 2 or any(kw in q for kw in ["nhieu nam", "5 nam", "3 nam", "gan day"]):
            return "trend_analysis"
    return "metric_lookup"


# ---------------------------------------------------------------------------
# Step 2: Entity Extractor
# ---------------------------------------------------------------------------

def _fuzzy_match_company(token: str, choices: list[str], cutoff: float = 0.75) -> Optional[str]:
    matches = difflib.get_close_matches(token, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def extract_entities(question: str, available_years: list[int], llm_router=None) -> dict:
    """Extract entities from question. Uses LLM if available, else regex fallback."""
    if llm_router:
        try:
            return _extract_entities_llm(question, available_years, llm_router)
        except Exception as e:
            logger.warning(f"[LLM entity extraction failed] {e}")

    return _extract_entities_fallback(question, available_years)


def _extract_entities_llm(question: str, available_years: list[int], llm_router) -> dict:
    """Use LLM to extract entities."""
    known_tickers = list(SUPPORTED_TICKERS.keys())
    system = textwrap.dedent(f"""
        Bạn là bộ trích xuất thực thể cho câu hỏi tài chính tiếng Việt.
        Danh sách mã công ty: {known_tickers}
        Năm có dữ liệu: {sorted(available_years)}
        Alias: {json.dumps(COMPANY_ALIASES, ensure_ascii=False)}

        Trả về JSON THUẦN, đúng schema:
        {{
          "companies": ["MÃ1"],
          "years": [2023],
          "metrics": ["doanh_thu_thuan"],
          "ratio": null,
          "top_n": 5,
          "is_concept_question": false
        }}

        Chỉ tiêu hợp lệ: {list(LINE_ITEM_PATTERNS.keys())}
        Nếu câu hỏi hỏi về khái niệm/định nghĩa, set is_concept_question=true.
    """).strip()

    response = llm_router.generate_for_task(
        question, system, task_type="entity_extraction", max_tokens=500
    )

    text = response.text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    entities = json.loads(text)
    entities.setdefault("companies", [])
    entities.setdefault("years", [max(available_years)] if available_years else [2024])
    entities.setdefault("metrics", ["doanh_thu_thuan"])
    entities.setdefault("ratio", None)
    entities.setdefault("top_n", 5)
    entities.setdefault("is_concept_question", False)
    return entities


def _extract_entities_fallback(question: str, available_years: list[int]) -> dict:
    """Regex + fuzzy match entity extraction."""
    q = _normalize(question)
    all_aliases = list(COMPANY_ALIASES.keys())
    all_tickers = list(SUPPORTED_TICKERS.keys())

    # Companies
    companies: list[str] = []
    for alias, ticker in COMPANY_ALIASES.items():
        if _normalize(alias) in q and ticker not in companies:
            companies.append(ticker)
    for ticker in all_tickers:
        if ticker.lower() in q.split() or ticker.lower() in q:
            if ticker not in companies:
                companies.append(ticker)
    if not companies:
        for token in q.split():
            if len(token) < 3:
                continue
            match = _fuzzy_match_company(token, [a.lower() for a in all_aliases])
            if match:
                ticker = COMPANY_ALIASES.get(match)
                if ticker and ticker not in companies:
                    companies.append(ticker)

    # Years
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", question)]
    n_years_match = re.search(r"(\d+)\s*nam\s*(gan day|truoc|qua|gan|recent)", q)
    if n_years_match:
        n = int(n_years_match.group(1))
        years = sorted(available_years)[-n:] if available_years else list(range(2024 - n + 1, 2025))
    if not years:
        years = [max(available_years)] if available_years else [2024]

    # Metrics
    metrics: list[str] = []
    metric_map = {
        "doanh_thu_thuan": ["doanh thu", "revenue", "doanh thu thuan"],
        "loi_nhuan_sau_thue": ["lợi nhuận sau thuế", "loi nhuan sau thue", "net profit", "lợi nhuận", "loi nhuan"],
        "loi_nhuan_truoc_thue": ["lợi nhuận trước thuế", "loi nhuan truoc thue"],
        "von_chu_so_huu": ["vốn chủ sở hữu", "von chu so huu", "equity", "vcsh"],
        "tong_tai_san": ["tổng tài sản", "tong tai san", "total assets"],
        "no_phai_tra": ["nợ phải trả", "no phai tra", "liabilities"],
    }
    q_norm = _normalize(question)
    for key, patterns in metric_map.items():
        for p in patterns:
            if _normalize(p) in q_norm and key not in metrics:
                metrics.append(key)
                break

    # Ratio
    ratio_found = None
    for rk in RATIO_DEFINITIONS:
        if rk in q_norm:
            ratio_found = rk
            break

    if not metrics and not ratio_found:
        metrics = ["doanh_thu_thuan"]

    # Top N
    top_n = 5
    top_match = re.search(r"top\s*(\d+)", q)
    if top_match:
        top_n = int(top_match.group(1))

    # Concept check
    is_concept = any(kw in q for kw in ["la gi", "giai thich", "dinh nghia", "khai niem", "cong thuc"])

    return {
        "companies": companies,
        "years": sorted(set(years)),
        "metrics": metrics,
        "ratio": ratio_found,
        "top_n": top_n,
        "is_concept_question": is_concept,
    }


# ---------------------------------------------------------------------------
# Main Agent (Orchestrator)
# ---------------------------------------------------------------------------

class FinancialAgent:
    """
    Multi-layer financial agent orchestrator.

    Wires together: Market Data → Knowledge → Retrieval → LLM → Tools
    """

    def __init__(
        self,
        dataset: Optional[pd.DataFrame] = None,
        llm_router=None,
        retriever=None,
        tool_registry=None,
        aggregator=None,
    ):
        self.dataset = dataset if dataset is not None else pd.DataFrame()

        # Lazy init layers
        self._llm_router = llm_router
        self._retriever = retriever
        self._tool_registry = tool_registry
        self._aggregator = aggregator

        # Compatibility fields used by earlier callers. The active provider is
        # still managed by LLMRouter (Groq/Ollama/Gemini).
        self.api_key = os.getenv("GROQ_API_KEY") or os.getenv("QROQ_API_KEY", "")
        self.model = os.getenv("GROQ_MODEL") or os.getenv("QROQ_MODEL", "")
        self.base_url = os.getenv("GROQ_BASE_URL") or os.getenv("QROQ_BASE_URL", "")
        self.llm_enabled = bool(self.api_key)

    @property
    def llm_router(self):
        if self._llm_router is None:
            try:
                from llm.router import LLMRouter
                self._llm_router = LLMRouter()
            except Exception as e:
                logger.warning(f"[Agent] Failed to init LLM router: {e}")
        return self._llm_router

    @property
    def retriever(self):
        if self._retriever is None:
            try:
                from retrieval.hybrid_retriever import HybridRetriever
                from knowledge.loader import KnowledgeBase
                kb = KnowledgeBase()
                self._retriever = HybridRetriever(
                    knowledge_base=kb,
                    use_reranker=True,
                    llm_router=self._llm_router,
                )
                self._retriever.build_index()
            except Exception as e:
                logger.warning(f"[Agent] Failed to init retriever: {e}")
        return self._retriever

    @property
    def tool_registry(self):
        if self._tool_registry is None:
            try:
                from tools.base import ToolRegistry
                from tools.stock_analysis import StockAnalysisTool
                from tools.economic_analysis import EconomicAnalysisTool
                from tools.explain_concept import ExplainConceptTool
                from tools.portfolio_metrics import PortfolioMetricsTool
                from tools.market_data import MarketDataTool

                registry = ToolRegistry()
                registry.register(StockAnalysisTool())
                registry.register(EconomicAnalysisTool())
                registry.register(ExplainConceptTool())
                registry.register(PortfolioMetricsTool())
                registry.register(MarketDataTool())
                self._tool_registry = registry
            except Exception as e:
                logger.warning(f"[Agent] Failed to init tools: {e}")
        return self._tool_registry

    @property
    def aggregator(self):
        """Initialize network-backed data sources only for a live-data query."""
        if self._aggregator is None:
            try:
                from market_data.aggregator import DataAggregator
                self._aggregator = DataAggregator()
            except Exception as exc:
                logger.warning("[Agent] Failed to init market data: %s", exc)
        return self._aggregator

    def update_dataset(self, df: pd.DataFrame) -> None:
        self.dataset = df

    def _get_available_years(self) -> list[int]:
        if self.dataset.empty or "year" not in self.dataset.columns:
            return list(range(2020, 2025))
        return sorted(self.dataset["year"].dropna().astype(int).unique().tolist())

    def answer(self, question: str) -> dict:
        """Run the shared orchestration pipeline.

        Step 1 routes the query; Step 2 extracts entities; Step 3 chooses a
        capability; Step 4 obtains facts; Step 5 optionally improves wording.
        The sequence is intentionally explicit so a LangGraph node can replace
        any step later without changing tools or API consumers.
        """

        # Step 1 — classify before reading data. Current values must be routed
        # to tools, while definitions and theories go to the knowledge layer.
        intent = classify_intent(question)
        logger.info(f"[INTENT] {intent}")

        # Step 2 — extract tickers, years and requested metrics deterministically
        # unless a preconfigured LLM router is explicitly provided.
        available_years = self._get_available_years()
        # Keep the deterministic parser as the zero-configuration path.  An
        # application that has already initialized an LLM router can opt into
        # LLM entity extraction without making every CLI request probe a local
        # Ollama server.
        llm_router = self._llm_router
        entities = extract_entities(question, available_years, llm_router)
        entities["_question"] = question
        logger.info(f"[ENTITIES] {entities}")

        # Ensure companies for non-ranking/concept intents
        if not entities.get("companies") and intent not in ("ranking", "concept_explain", "economic_analysis", "portfolio"):
            if not self.dataset.empty:
                entities["companies"] = self.dataset["company_code"].unique().tolist()[:3]

        # Step 3 — select exactly one boundary tool for the request type.
        tool = None
        if self.tool_registry:
            tool = self.tool_registry.select_tool(intent, entities)

        # Step 4 — retrieve/calculation happens inside the selected tool. This
        # keeps market data, RAG context and computations isolated from routing.
        tool_name = "none"
        knowledge_refs = []
        citations = []

        if tool:
            tool_name = tool.name
            context = {
                "dataset": self.dataset,
                "retriever": self.retriever if intent in ("concept_explain", "economic_analysis", "market_and_knowledge") else self._retriever,
                "llm_router": llm_router,
                "aggregator": self.aggregator if intent in ("market_data", "market_and_knowledge", "portfolio") else self._aggregator,
            }
            tool_result = tool.execute(
                {"intent": intent, "entities": entities},
                context,
            )

            if tool_result.success:
                answer_text = tool_result.answer_text
                chart_data = tool_result.chart_data
                knowledge_refs = tool_result.knowledge_refs
                citations = tool_result.citations
                confidence = 0.85
            else:
                answer_text = tool_result.error or "Không thể xử lý câu hỏi này."
                chart_data = None
                confidence = 0.2
                citations = tool_result.citations
        else:
            answer_text = "Không tìm thấy công cụ phù hợp để xử lý câu hỏi."
            chart_data = None
            confidence = 0.1

        # Step 5 — an LLM may polish already-grounded stock-analysis output; it
        # is never asked to invent or recalculate returned numerical facts.
        llm_provider = "none"
        if llm_router and tool_name == "stock_analysis" and len(answer_text) < 2000:
            try:
                polish_prompt = textwrap.dedent(f"""
                    Câu hỏi: {question}
                    Dữ liệu đã tính:
                    {answer_text}

                    Viết lại ngắn gọn, chuyên nghiệp bằng tiếng Việt.
                    Giữ nguyên tất cả con số. Không thêm thông tin ngoài dữ liệu đã có.
                    Nếu có thông tin nguồn, hãy ghi chú 'Nguồn: ...' ở cuối.
                """).strip()
                response = llm_router.generate_for_task(
                    polish_prompt, task_type="polish", max_tokens=600
                )
                if response.text and not response.error:
                    answer_text = response.text
                    llm_provider = f"{response.provider}/{response.model}"
            except Exception as e:
                logger.warning(f"[LLM polish failed] {e}")

        if llm_router:
            llm_provider = llm_provider if llm_provider != "none" else (
                f"{llm_router.active_provider}" if llm_router.active_provider else "none"
            )

        return {
            "answer": answer_text,
            "chart_type": chart_data.get("type") if chart_data else None,
            "chart_data": chart_data,
            "citations": citations,
            "confidence": round(min(max(confidence, 0.0), 1.0), 2),
            "intent": intent,
            "entities": {k: v for k, v in entities.items() if not k.startswith("_")},
            "cached": True,
            "tool_used": tool_name,
            "knowledge_refs": knowledge_refs,
            "llm_provider": llm_provider,
        }
