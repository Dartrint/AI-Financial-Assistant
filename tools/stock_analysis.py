"""
tools/stock_analysis.py
Stock analysis tool — handles metric lookup, trends, comparisons, ratios, rankings.
Refactored computation logic from the original agent.py.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

import pandas as pd

from config import RATIO_DEFINITIONS, SUPPORTED_TICKERS
from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


def _format_number(value: Any) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return "N/A"
    if abs(v) >= 1e12:
        return f"{v / 1e12:,.2f} nghìn tỷ VND"
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f} tỷ VND"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.2f} triệu VND"
    return f"{v:,.0f} VND"


def _format_percent(v: float) -> str:
    if math.isnan(v) or math.isinf(v):
        return "N/A"
    return f"{v:.2f}%"


def _get_value(df: pd.DataFrame, metric: str, company: str, year: int) -> Optional[float]:
    rows = df[
        (df["company_code"] == company)
        & (df["year"] == year)
        & (df["line_item_normalized"] == metric)
    ]
    if rows.empty:
        return None
    return float(rows["value"].sum())


class StockAnalysisTool(Tool):
    """Comprehensive stock analysis: lookup, trends, comparison, ratios, ranking."""

    @property
    def name(self) -> str:
        return "stock_analysis"

    @property
    def description(self) -> str:
        return "Phân tích cổ phiếu: tra cứu chỉ tiêu BCTC, xu hướng nhiều năm, so sánh công ty, tính tỷ số tài chính, xếp hạng."

    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        intent = params.get("intent", "metric_lookup")
        entities = params.get("entities", {})
        dataset = context.get("dataset", pd.DataFrame())

        if dataset.empty:
            return ToolResult(success=False, error="Không có dữ liệu")

        # Retrieve relevant data
        df = self._retrieve_data(dataset, entities, intent)

        # Compute based on intent
        if intent == "metric_lookup":
            return self._metric_lookup(df, entities)
        elif intent == "trend_analysis":
            return self._trend_analysis(df, entities)
        elif intent == "comparison":
            return self._comparison(df, entities)
        elif intent == "ratio_calc":
            return self._ratio_calc(df, entities)
        elif intent == "ranking":
            return self._ranking(df, entities)
        else:
            return self._metric_lookup(df, entities)

    def _retrieve_data(self, df: pd.DataFrame, entities: dict, intent: str) -> pd.DataFrame:
        companies = entities.get("companies", [])
        years = entities.get("years", [])
        metrics = entities.get("metrics", [])
        ratio = entities.get("ratio")

        if intent == "ranking" and not companies:
            companies = df["company_code"].unique().tolist()

        result = df.copy()
        if companies:
            result = result[result["company_code"].isin(companies)]
        if years:
            result = result[result["year"].isin(years)]

        needed_metrics = list(metrics)
        if ratio and ratio in RATIO_DEFINITIONS:
            rd = RATIO_DEFINITIONS[ratio]
            needed_metrics.extend([rd["numerator"], rd["denominator"]])

        if needed_metrics:
            filtered = result[result["line_item_normalized"].isin(needed_metrics)]
            if not filtered.empty:
                result = filtered

        return result

    def _metric_lookup(self, df: pd.DataFrame, entities: dict) -> ToolResult:
        if df.empty:
            return ToolResult(success=False, error="Không tìm thấy dữ liệu")

        metric = entities.get("metrics", [None])[0] if entities.get("metrics") else None
        if metric:
            metric_df = df[df["line_item_normalized"] == metric]
        else:
            metric_df = df

        parts = []
        for _, row in metric_df.sort_values(["company_code", "year"]).iterrows():
            parts.append(f"• {row['company_code']} năm {int(row['year'])}: {_format_number(row['value'])}")

        answer = f"**{metric or 'Chỉ tiêu'}**:\n" + "\n".join(parts) if parts else "Không có dữ liệu."

        chart_data = None
        if len(metric_df) > 1:
            items = metric_df.to_dict("records")
            labels = [f"{r['company_code']} {int(r['year'])}" for r in items]
            values = [float(r["value"]) / 1e9 for r in items]
            chart_data = {
                "type": "bar", "labels": labels,
                "datasets": [{"label": metric or "Giá trị", "values": values}],
                "title": f"Kết quả {metric or ''}", "unit": "tỷ VND",
            }

        return ToolResult(success=True, answer_text=answer, chart_data=chart_data)

    def _trend_analysis(self, df: pd.DataFrame, entities: dict) -> ToolResult:
        if df.empty:
            return ToolResult(success=False, error="Không có dữ liệu xu hướng")

        metric = entities.get("metrics", [None])[0] if entities.get("metrics") else None
        companies = entities.get("companies") or df["company_code"].unique().tolist()

        answer_parts = []
        datasets = []

        for company in companies:
            comp_df = df[df["company_code"] == company]
            if metric:
                comp_df = comp_df[comp_df["line_item_normalized"] == metric]
            if comp_df.empty:
                continue

            yearly = comp_df.groupby("year")["value"].sum().sort_index()
            values_by_year = {int(k): float(v) for k, v in yearly.items()}
            years_list = sorted(values_by_year.keys())

            if len(years_list) < 1:
                continue

            # YoY growth
            yoy = {}
            prev = None
            for y in years_list:
                if prev is not None and prev != 0:
                    yoy[y] = round((values_by_year[y] - prev) / abs(prev) * 100, 2)
                prev = values_by_year[y]

            # CAGR
            cagr = None
            if len(years_list) >= 2:
                fv, lv = values_by_year[years_list[0]], values_by_year[years_list[-1]]
                n = years_list[-1] - years_list[0]
                if fv > 0 and n > 0:
                    cagr = round(((lv / fv) ** (1 / n) - 1) * 100, 2)

            first_yr, last_yr = years_list[0], years_list[-1]
            text = f"{company}: {_format_number(values_by_year[first_yr])} ({first_yr}) → {_format_number(values_by_year[last_yr])} ({last_yr})"
            if cagr is not None:
                text += f", CAGR {cagr:+.2f}%/năm"
            if yoy:
                yoy_str = ", ".join(f"{y}: {g:+.1f}%" for y, g in sorted(yoy.items()))
                text += f"\n  YoY: {yoy_str}"
            answer_parts.append(text)

            datasets.append({
                "label": company,
                "values": [values_by_year.get(y, 0) / 1e9 for y in years_list],
            })

        answer = f"**Xu hướng {metric or ''}**:\n" + "\n".join(answer_parts)
        chart_data = None
        if datasets:
            all_years = sorted(set(int(y) for y in df["year"].unique()))
            chart_data = {
                "type": "line",
                "labels": [str(y) for y in all_years],
                "datasets": datasets,
                "title": f"Xu hướng {metric or ''}", "unit": "tỷ VND",
            }

        return ToolResult(success=True, answer_text=answer, chart_data=chart_data)

    def _comparison(self, df: pd.DataFrame, entities: dict) -> ToolResult:
        if df.empty:
            return ToolResult(success=False, error="Không có dữ liệu so sánh")

        metric = entities.get("metrics", [None])[0] if entities.get("metrics") else None
        years = sorted(entities.get("years") or df["year"].unique().tolist())
        year = max(years) if years else None

        metric_df = df[df["line_item_normalized"] == metric] if metric else df
        if year:
            metric_df = metric_df[metric_df["year"] == year]

        grouped = metric_df.groupby("company_code")["value"].sum().sort_values(ascending=False)
        parts = [f"  {i+1}. {c}: {_format_number(v)}" for i, (c, v) in enumerate(grouped.items())]
        answer = f"**So sánh {metric or ''}** năm {year}:\n" + "\n".join(parts)

        chart_data = {
            "type": "bar",
            "labels": list(grouped.index),
            "datasets": [{"label": metric or "Giá trị", "values": [float(v) / 1e9 for v in grouped.values]}],
            "title": f"So sánh {metric or ''} năm {year}", "unit": "tỷ VND",
        }

        return ToolResult(success=True, answer_text=answer, chart_data=chart_data)

    def _ratio_calc(self, df: pd.DataFrame, entities: dict) -> ToolResult:
        ratio_key = entities.get("ratio")
        if not ratio_key or ratio_key not in RATIO_DEFINITIONS:
            return ToolResult(success=False, error=f"Tỷ số không hợp lệ: {ratio_key}")

        rd = RATIO_DEFINITIONS[ratio_key]
        companies = entities.get("companies") or df["company_code"].unique().tolist()
        years = sorted(entities.get("years") or df["year"].unique().tolist())

        parts = []
        labels, values = [], []
        for company in companies:
            for year in years:
                num = _get_value(df, rd["numerator"], company, year)
                den = _get_value(df, rd["denominator"], company, year)
                if num is None or den is None or den == 0:
                    continue
                ratio_val = (num / den) * 100 if rd["format"] == "percent" else num / den
                val_str = _format_percent(ratio_val) if rd["format"] == "percent" else f"{ratio_val:.2f} lần"
                parts.append(f"• {company} {year}: {val_str}")
                labels.append(f"{company} {year}")
                values.append(round(ratio_val, 2))

        answer = f"**{rd['label']}**:\n" + "\n".join(parts) if parts else f"Không thể tính {ratio_key}"
        chart_data = {
            "type": "bar", "labels": labels,
            "datasets": [{"label": rd["label"], "values": values}],
            "title": rd["label"],
            "unit": "%" if rd["format"] == "percent" else "lần",
        } if labels else None

        return ToolResult(success=True, answer_text=answer, chart_data=chart_data)

    def _ranking(self, df: pd.DataFrame, entities: dict) -> ToolResult:
        if df.empty:
            return ToolResult(success=False, error="Không có dữ liệu xếp hạng")

        metric = entities.get("metrics", [None])[0] if entities.get("metrics") else None
        years = sorted(entities.get("years") or df["year"].unique().tolist())
        year = max(years) if years else None
        top_n = entities.get("top_n", 5)

        metric_df = df[df["line_item_normalized"] == metric] if metric else df
        if year:
            metric_df = metric_df[metric_df["year"] == year]

        grouped = metric_df.groupby("company_code")["value"].sum().sort_values(ascending=False).head(top_n)
        parts = [f"  {i+1}. {c}: {_format_number(v)}" for i, (c, v) in enumerate(grouped.items())]
        answer = f"**Top {top_n} {metric or ''}** năm {year}:\n" + "\n".join(parts)

        chart_data = {
            "type": "bar",
            "labels": list(grouped.index),
            "datasets": [{"label": metric or "Giá trị", "values": [float(v) / 1e9 for v in grouped.values]}],
            "title": f"Top {top_n} - {metric or ''} năm {year}", "unit": "tỷ VND",
        }

        return ToolResult(success=True, answer_text=answer, chart_data=chart_data)
