"""
market_data/ecodata_source.py
EcoData.ai API integration — refactored into DataSource interface.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import requests
from dotenv import load_dotenv

from config import LINE_ITEM_PATTERNS, SUPPORTED_TICKERS
from market_data.base import DataSource, HealthStatus

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

logger = logging.getLogger(__name__)

ECODATA_API_KEY = os.getenv("ECODATA_API_KEY", "")
ECODATA_BASE_URL = os.getenv("ECODATA_BASE_URL", "https://api.ecodata.ai/v1")
ECODATA_MACRO_PATH = os.getenv("ECODATA_MACRO_PATH", "/macro/{indicator}")
ECODATA_QUOTE_PATH = os.getenv("ECODATA_QUOTE_PATH", "/stocks/{ticker}/quote")

STATEMENT_TYPE_MAP = {
    "income_statement": "ket_qua_kinh_doanh",
    "balance_sheet": "bang_can_doi_ke_toan",
    "cash_flow": "luu_chuyen_tien_te",
}


def _normalize_line_item(raw_name: str) -> str | None:
    key = raw_name.lower().strip()
    for normalized, patterns in LINE_ITEM_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in key:
                return normalized
    return None


def _make_request(endpoint: str, params: dict | None = None, timeout: int = 15) -> dict:
    if not ECODATA_API_KEY:
        raise ValueError("ECODATA_API_KEY not configured")
    url = f"{ECODATA_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {ECODATA_API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


class EcoDataSource(DataSource):
    """EcoData.ai structured financial data API."""

    @property
    def name(self) -> str:
        return "ecodata"

    def supported_tickers(self) -> list[str]:
        return list(SUPPORTED_TICKERS.keys())

    def health_check(self) -> HealthStatus:
        if not ECODATA_API_KEY:
            return HealthStatus(
                source_name="ecodata", available=False,
                message="ECODATA_API_KEY not configured",
            )
        try:
            _make_request("/stocks/VCB/profile", timeout=5)
            return HealthStatus(
                source_name="ecodata", available=True,
                message="EcoData API reachable",
            )
        except requests.exceptions.ConnectionError:
            return HealthStatus(
                source_name="ecodata", available=False,
                message="EcoData API endpoint not reachable",
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return HealthStatus(
                    source_name="ecodata", available=True,
                    message="Invalid API key",
                )
            return HealthStatus(
                source_name="ecodata", available=False,
                message=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            return HealthStatus(
                source_name="ecodata", available=False,
                message=str(e)[:150],
            )

    def _fetch_statement(
        self, ticker: str, statement_type: str, years: list[int]
    ) -> pd.DataFrame:
        endpoint = f"/stocks/{ticker}/statements/{statement_type}"
        params = {"period": "annual", "years": ",".join(map(str, years))}

        try:
            response = _make_request(endpoint, params)
        except Exception as e:
            logger.warning(f"[ecodata] Failed {ticker} {statement_type}: {e}")
            return pd.DataFrame()

        rows = []
        stmt_normalized = STATEMENT_TYPE_MAP.get(statement_type, statement_type)
        for year_data in response.get("data", []):
            year = year_data.get("year")
            for item in year_data.get("line_items", []):
                name = item.get("name", "")
                value = item.get("value")
                if not name or value is None:
                    continue
                rows.append({
                    "company_code": ticker,
                    "company_name": SUPPORTED_TICKERS.get(ticker, ticker),
                    "year": int(year),
                    "statement_type": stmt_normalized,
                    "line_item": name,
                    "line_item_normalized": _normalize_line_item(name),
                    "value": float(value),
                    "unit": item.get("unit", "VND"),
                    "source_file": f"ecodata:{ticker}:{statement_type}",
                    "source_page": f"EcoData API - {statement_type} {year}",
                })
        return pd.DataFrame(rows)

    def fetch(self, ticker: str, years: list[int]) -> pd.DataFrame:
        frames = []
        for stmt in ["income_statement", "balance_sheet", "cash_flow"]:
            df = self._fetch_statement(ticker, stmt, years)
            if not df.empty:
                frames.append(df)
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            logger.info(f"[ecodata] {ticker}: {len(combined)} rows")
            return combined
        return pd.DataFrame()

    def fetch_macro(self, indicator: str) -> dict:
        """Return a macro observation without fabricating a value on failure."""
        response = _make_request(ECODATA_MACRO_PATH.format(indicator=indicator))
        payload = response.get("data", response)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict) or payload.get("value") is None:
            return {}
        return {
            "indicator": indicator,
            "value": payload["value"],
            "unit": payload.get("unit", ""),
            "period": payload.get("period") or payload.get("date") or "mới nhất",
            "source": "EcoData",
        }

    def fetch_market_info(self, ticker: str) -> dict:
        """Read a configured EcoData quote endpoint when it is available."""
        response = _make_request(ECODATA_QUOTE_PATH.format(ticker=ticker))
        payload = response.get("data", response)
        if not isinstance(payload, dict):
            return {}
        aliases = {
            "current_price": ("current_price", "price", "last_price"),
            "pe_ratio": ("pe_ratio", "pe", "trailing_pe"),
            "pb_ratio": ("pb_ratio", "pb", "price_to_book"),
            "market_cap": ("market_cap", "marketCapitalization"),
            "dividend_yield": ("dividend_yield", "dividendYield"),
        }
        result = {key: next((payload.get(name) for name in names if payload.get(name) is not None), None)
                  for key, names in aliases.items()}
        result["currency"] = payload.get("currency", "VND")
        return {key: value for key, value in result.items() if value is not None}
