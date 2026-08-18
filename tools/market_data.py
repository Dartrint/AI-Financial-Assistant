"""Live market and macro-data tool.

Live values are intentionally separate from the annual-report and RAG paths,
so the assistant never presents a stale document as a current market value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.base import Tool, ToolResult


_METRICS = {
    "current_price": "Giá hiện tại",
    "pe_ratio": "P/E trailing",
    "pb_ratio": "P/B",
    "market_cap": "Vốn hóa thị trường",
    "dividend_yield": "Lợi suất cổ tức",
    "52w_high": "Đỉnh 52 tuần",
    "52w_low": "Đáy 52 tuần",
}


def _format_value(key: str, value: Any, currency: str = "VND") -> str:
    number = float(value)
    if key == "market_cap":
        return f"{number:,.0f} {currency}"
    if key == "dividend_yield":
        return f"{number * 100:.2f}%" if abs(number) <= 1 else f"{number:.2f}%"
    if key in {"pe_ratio", "pb_ratio"}:
        return f"{number:.2f}x"
    return f"{number:,.2f} {currency}"


def _requested_metrics(question: str) -> list[str]:
    q = question.lower()
    aliases = {
        "current_price": ("giá", "gia", "price", "thị giá", "thi gia"),
        "pe_ratio": ("p/e", "pe ", "trailing pe"),
        "pb_ratio": ("p/b", "pb ", "price to book"),
        "market_cap": ("vốn hóa", "von hoa", "market cap"),
        "dividend_yield": ("cổ tức", "co tuc", "dividend"),
    }
    requested = [key for key, words in aliases.items() if any(word in q for word in words)]
    return requested or ["current_price", "pe_ratio", "pb_ratio"]


def _macro_indicator(question: str) -> str | None:
    q = question.lower()
    for indicator, aliases in {
        "cpi": ("cpi", "lạm phát", "lam phat", "inflation"),
        "gdp": ("gdp",),
        "policy_rate": ("lãi suất", "lai suat", "policy rate"),
        "exchange_rate": ("tỷ giá", "ty gia", "exchange rate"),
    }.items():
        if any(alias in q for alias in aliases):
            return indicator
    return None


class MarketDataTool(Tool):
    """Fetch current quotes/macro observations and optionally add RAG context."""

    @property
    def name(self) -> str:
        return "market_data"

    @property
    def description(self) -> str:
        return "Tra cứu dữ liệu thị trường và vĩ mô mới nhất; có thể diễn giải theo tri thức RAG."

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        entities = params.get("entities", {})
        question = entities.get("_question", "")
        aggregator = context.get("aggregator")
        intent = params.get("intent", "market_data")
        if aggregator is None:
            return ToolResult(success=False, error="Lớp dữ liệu thị trường chưa sẵn sàng.")

        indicator = _macro_indicator(question)
        if indicator and not entities.get("companies"):
            return self._macro_answer(aggregator, indicator)

        companies = entities.get("companies") or []
        if not companies:
            return ToolResult(success=False, error="Hãy cho biết mã cổ phiếu, ví dụ FPT hoặc VCB.")

        ticker = companies[0]
        try:
            info = aggregator.fetch_market_info(ticker) or {}
        except Exception as exc:
            return ToolResult(success=False, error=f"Không thể lấy dữ liệu thị trường cho {ticker}: {exc}")
        if not info:
            return ToolResult(success=False, error=f"Chưa lấy được dữ liệu thị trường mới nhất cho {ticker}.")

        currency = str(info.get("currency") or "VND")
        metrics = _requested_metrics(question)
        rows = []
        for key in metrics:
            if info.get(key) is None:
                continue
            try:
                rows.append(f"- {_METRICS[key]}: {_format_value(key, info[key], currency)}")
            except (TypeError, ValueError):
                continue
        if not rows:
            return ToolResult(success=False, error=f"Nguồn dữ liệu không trả về chỉ tiêu được hỏi cho {ticker}.")

        answer = f"**Dữ liệu thị trường {ticker}**\n" + "\n".join(rows)
        sources = info.get("data_sources") or ["Yahoo Finance"]
        source_label = ", ".join(str(source) for source in sources)
        answer += f"\n\nNguồn: {source_label}; dữ liệu có thể trễ so với giao dịch thực tế."
        refs: list[str] = []
        if intent == "market_and_knowledge":
            interpretation, refs = self._interpret(question, info, context)
            answer += f"\n\n**Diễn giải**\n{interpretation}"
        return ToolResult(
            success=True,
            data={key: info.get(key) for key in metrics},
            answer_text=answer,
            citations=[{"source": source_label, "ticker": ticker, "retrieved_at": datetime.now(timezone.utc).isoformat()}],
            knowledge_refs=refs,
        )

    def _macro_answer(self, aggregator: Any, indicator: str) -> ToolResult:
        try:
            record = aggregator.fetch_macro(indicator) or {}
        except Exception as exc:
            return ToolResult(success=False, error=f"Không thể lấy {indicator.upper()} mới nhất: {exc}")
        if record.get("value") is None:
            return ToolResult(success=False, error=f"Chưa có nguồn EcoData đã cấu hình để lấy {indicator.upper()} thời gian thực.")
        unit, period = record.get("unit", ""), record.get("period", "mới nhất")
        answer = f"**{indicator.upper()} ({period})**: {record['value']} {unit}".strip()
        return ToolResult(success=True, data=record, answer_text=answer,
                          citations=[{"source": record.get("source", "EcoData"), "indicator": indicator, "period": period}])

    def _interpret(self, question: str, info: dict[str, Any], context: dict[str, Any]) -> tuple[str, list[str]]:
        refs: list[str] = []
        retriever = context.get("retriever")
        if retriever:
            try:
                refs = [f"{r.document.category}/{r.document.title}" for r in retriever.search(question, top_k=2)]
            except Exception:
                pass
        try:
            pe = float(info["pe_ratio"])
            return (f"P/E hiện tại là {pe:.2f}x. P/E cao hay thấp chỉ có ý nghĩa khi so với lịch sử của doanh nghiệp, các công ty cùng ngành và triển vọng tăng trưởng/lợi nhuận; không nên dùng một ngưỡng cố định để kết luận cổ phiếu đắt hay rẻ.", refs)
        except (KeyError, TypeError, ValueError):
            return ("Cần đặt chỉ tiêu cạnh lịch sử doanh nghiệp, nhóm ngành và chất lượng lợi nhuận trước khi đưa ra đánh giá.", refs)
