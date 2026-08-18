"""
tools/portfolio_metrics.py
Portfolio metrics tool — calculates portfolio return, risk, Sharpe, correlation.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class PortfolioMetricsTool(Tool):
    """Calculate portfolio metrics: returns, risk, Sharpe ratio, correlation."""

    @property
    def name(self) -> str:
        return "portfolio_metrics"

    @property
    def description(self) -> str:
        return "Tính toán chỉ số danh mục đầu tư: lợi nhuận, rủi ro, Sharpe ratio, tương quan giữa các cổ phiếu."

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        entities = params.get("entities", {})
        aggregator = context.get("aggregator")
        companies = entities.get("companies", [])

        if not companies or len(companies) < 2:
            return ToolResult(
                success=False,
                error="Cần ít nhất 2 mã cổ phiếu để phân tích danh mục.",
            )

        # Get price history for each ticker
        price_data = {}
        if aggregator:
            for ticker in companies:
                try:
                    hist = aggregator.fetch_price_history(ticker, period="2y")
                    if not hist.empty and "Close" in hist.columns:
                        price_data[ticker] = hist["Close"]
                except Exception as e:
                    logger.warning(f"[Portfolio] No price data for {ticker}: {e}")

        if len(price_data) < 2:
            # Fallback: use BCTC data to calculate simple metrics
            return self._fallback_metrics(entities, context)

        # Align price data
        price_df = pd.DataFrame(price_data).dropna()
        if len(price_df) < 20:
            return self._fallback_metrics(entities, context)

        # Calculate returns
        returns_df = price_df.pct_change().dropna()

        # Equal-weight portfolio
        n = len(companies)
        weights = np.array([1.0 / n] * n)

        # Individual stats
        individual_stats = []
        for ticker in companies:
            if ticker in returns_df.columns:
                ret = returns_df[ticker]
                ann_return = float(ret.mean() * 252 * 100)
                ann_vol = float(ret.std() * np.sqrt(252) * 100)
                individual_stats.append({
                    "ticker": ticker,
                    "annual_return": round(ann_return, 2),
                    "annual_volatility": round(ann_vol, 2),
                })

        # Portfolio stats
        port_returns = returns_df.dot(weights)
        port_ann_return = float(port_returns.mean() * 252 * 100)
        port_ann_vol = float(port_returns.std() * np.sqrt(252) * 100)

        # Sharpe ratio (assume risk-free rate = 5% for Vietnam)
        risk_free = 5.0
        sharpe = (port_ann_return - risk_free) / port_ann_vol if port_ann_vol > 0 else 0

        # Correlation matrix
        corr_matrix = returns_df.corr()

        # Build answer
        parts = ["**Chỉ số từng cổ phiếu:**"]
        for s in individual_stats:
            parts.append(f"  • {s['ticker']}: Return {s['annual_return']:+.2f}%/năm, Vol {s['annual_volatility']:.2f}%")

        parts.append(f"\n**Danh mục (trọng số đều {100/n:.0f}% mỗi CP):**")
        parts.append(f"  • Return: {port_ann_return:+.2f}%/năm")
        parts.append(f"  • Volatility: {port_ann_vol:.2f}%")
        parts.append(f"  • Sharpe Ratio: {sharpe:.3f}")
        parts.append(f"  • Lãi suất phi rủi ro: {risk_free:.1f}%")

        parts.append("\n**Ma trận tương quan:**")
        for i, t1 in enumerate(companies):
            for t2 in companies[i + 1:]:
                if t1 in corr_matrix.index and t2 in corr_matrix.columns:
                    corr = corr_matrix.loc[t1, t2]
                    parts.append(f"  • {t1} ↔ {t2}: {corr:.3f}")

        answer = "\n".join(parts)

        # Chart: bar chart of individual returns
        chart_data = {
            "type": "bar",
            "labels": [s["ticker"] for s in individual_stats],
            "datasets": [
                {"label": "Return (%/năm)", "values": [s["annual_return"] for s in individual_stats]},
            ],
            "title": "Lợi nhuận hàng năm", "unit": "%",
        }

        return ToolResult(
            success=True,
            answer_text=answer,
            chart_data=chart_data,
            data={
                "individual": individual_stats,
                "portfolio_return": port_ann_return,
                "portfolio_vol": port_ann_vol,
                "sharpe": sharpe,
            },
        )

    def _fallback_metrics(self, entities: dict, context: dict) -> ToolResult:
        """Fallback when price data unavailable — use BCTC to compare."""
        dataset = context.get("dataset", pd.DataFrame())
        companies = entities.get("companies", [])

        if dataset.empty:
            return ToolResult(success=False, error="Không có dữ liệu giá hoặc BCTC")

        parts = ["**Thông tin BCTC (không có dữ liệu giá để tính portfolio metrics):**"]
        for company in companies:
            comp_df = dataset[dataset["company_code"] == company]
            if comp_df.empty:
                continue
            latest_year = int(comp_df["year"].max())
            latest = comp_df[comp_df["year"] == latest_year]
            revenue = latest[latest["line_item_normalized"] == "doanh_thu_thuan"]["value"].sum()
            profit = latest[latest["line_item_normalized"] == "loi_nhuan_sau_thue"]["value"].sum()
            parts.append(f"  • {company} ({latest_year}): DT {revenue/1e9:.1f} tỷ, LNST {profit/1e9:.1f} tỷ")

        return ToolResult(
            success=True,
            answer_text="\n".join(parts),
        )
