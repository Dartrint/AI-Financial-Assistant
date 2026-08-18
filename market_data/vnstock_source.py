"""
market_data/vnstock_source.py
Vietnam stock market data via vnstock library (VCI/TCBS APIs).

Implements the market-data interface used by the shared aggregator.
Includes: CSV cache, rate-limit handling, melt report logic, mock fallback.
"""

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    DEFAULT_SOURCE,
    LINE_ITEM_PATTERNS,
    SUPPORTED_TICKERS,
)
from market_data.base import DataSource, HealthStatus

logger = logging.getLogger(__name__)

os.makedirs(CACHE_DIR, exist_ok=True)

# Statement type mapping
STATEMENT_MAP = {
    "balance_sheet": "bang_can_doi_ke_toan",
    "income_statement": "ket_qua_kinh_doanh",
    "cash_flow": "luu_chuyen_tien_te",
}

NON_METRIC_COLS = {
    "ticker", "yearReport", "lengthReport", "year", "quarter", "period",
    "Meta_Ticker", "Meta_Year", "Meta_Quarter", "CP", "Năm", "Kỳ",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _normalize_line_item(raw_name: str) -> Optional[str]:
    key = _strip_accents(str(raw_name)).lower()
    for normalized, patterns in LINE_ITEM_PATTERNS.items():
        for p in patterns:
            if _strip_accents(p).lower() in key:
                return normalized
    return None


def _melt_report(df: pd.DataFrame, symbol: str, statement_key: str) -> pd.DataFrame:
    """Convert vnstock report (wide format) to long format."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # --- Item-rows format (vnstock VCI) ---
    item_col = None
    for cand in ["item", "item_en"]:
        if cand in df.columns:
            item_col = cand
            break

    if item_col is not None:
        year_cols = [
            col for col in df.columns
            if re.match(r"^20\d{2}$", str(col).strip())
        ]
        if not year_cols:
            return pd.DataFrame()

        rows = []
        for _, row in df.iterrows():
            item_name = str(row.get("item", row.get("item_en", ""))).strip()
            if not item_name:
                continue
            for year_col in year_cols:
                val = row[year_col]
                if pd.isna(val):
                    continue
                try:
                    float_val = float(val)
                except (ValueError, TypeError):
                    continue
                year_int = int(str(year_col).strip())
                rows.append({
                    "company_code": symbol,
                    "company_name": SUPPORTED_TICKERS.get(symbol, symbol),
                    "year": year_int,
                    "statement_type": STATEMENT_MAP[statement_key],
                    "line_item": item_name,
                    "line_item_normalized": _normalize_line_item(item_name),
                    "value": float_val,
                    "unit": "VND",
                    "source_file": f"vnstock:{DEFAULT_SOURCE}:{symbol}:{statement_key}",
                    "source_page": (
                        f"BCTC {year_int} - {STATEMENT_MAP[statement_key]} "
                        f"(API {DEFAULT_SOURCE})"
                    ),
                })
        return pd.DataFrame(rows).drop_duplicates()

    # --- Legacy format: rows=periods, cols=metrics ---
    year_col = None
    for cand in ["yearReport", "year", "Năm", "Year"]:
        if cand in df.columns:
            year_col = cand
            break
    if year_col is None:
        df = df.reset_index()
        for cand in df.columns:
            if "year" in str(cand).lower() or "năm" in str(cand).lower():
                year_col = cand
                break
    if year_col is None:
        return pd.DataFrame()

    metric_cols = [c for c in df.columns if c not in NON_METRIC_COLS and c != year_col]
    rows = []
    for _, row in df.iterrows():
        year_val = row[year_col]
        try:
            year_int = int(str(year_val).split(".")[0])
        except (ValueError, TypeError):
            continue
        for col in metric_cols:
            val = row[col]
            if pd.isna(val):
                continue
            try:
                float_val = float(val)
            except (ValueError, TypeError):
                continue
            rows.append({
                "company_code": symbol,
                "company_name": SUPPORTED_TICKERS.get(symbol, symbol),
                "year": year_int,
                "statement_type": STATEMENT_MAP[statement_key],
                "line_item": col,
                "line_item_normalized": _normalize_line_item(col),
                "value": float_val,
                "unit": "VND",
                "source_file": f"vnstock:{DEFAULT_SOURCE}:{symbol}:{statement_key}",
                    "source_page": (
                        f"BCTC {year_int} - {STATEMENT_MAP[statement_key]} "
                        f"(API {DEFAULT_SOURCE})"
                    ),
                })
    return pd.DataFrame(rows).drop_duplicates()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(symbol: str, year: int) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}_{year}.csv")


def _is_cache_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < CACHE_TTL_HOURS


def _load_cache(symbol: str, year: int) -> Optional[pd.DataFrame]:
    path = _cache_path(symbol, year)
    if _is_cache_fresh(path):
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            return df
        except Exception as e:
            logger.warning(f"[CACHE READ ERROR] {symbol} {year}: {e}")
    return None


def _save_cache(df: pd.DataFrame, symbol: str, year: int) -> None:
    path = _cache_path(symbol, year)
    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as e:
        logger.warning(f"[CACHE WRITE ERROR] {symbol} {year}: {e}")


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

def _generate_mock(symbol: str, years: list[int]) -> pd.DataFrame:
    """Generate mock data for testing when vnstock is unavailable."""
    import random
    random.seed(hash(symbol) % 10_000)
    rows = []
    base_revenue = random.uniform(5e12, 5e13)
    base_equity = random.uniform(1e13, 3e13)
    for i, year in enumerate(years):
        revenue = base_revenue * (1.08 ** i) * random.uniform(0.95, 1.05)
        net_profit = revenue * random.uniform(0.08, 0.15)
        equity = base_equity * (1.06 ** i)
        total_assets = equity * random.uniform(2.5, 4.0)
        items = [
            ("ket_qua_kinh_doanh", "Doanh thu thuần", "doanh_thu_thuan", revenue),
            ("ket_qua_kinh_doanh", "Lợi nhuận sau thuế TNDN",
             "loi_nhuan_sau_thue", net_profit),
            ("bang_can_doi_ke_toan", "Vốn chủ sở hữu", "von_chu_so_huu", equity),
            ("bang_can_doi_ke_toan", "Tổng cộng tài sản", "tong_tai_san", total_assets),
        ]
        for st, li, norm, val in items:
            rows.append({
                "company_code": symbol,
                "company_name": SUPPORTED_TICKERS.get(symbol, symbol),
                "year": year,
                "statement_type": st,
                "line_item": li,
                "line_item_normalized": norm,
                "value": val,
                "unit": "VND",
                "source_file": "MOCK_DATA",
                "source_page": f"[MOCK] {symbol} {year} - {st}",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# VnstockSource
# ---------------------------------------------------------------------------

class VnstockSource(DataSource):
    """Vietnam stock market data via vnstock library."""

    @property
    def name(self) -> str:
        return "vnstock"

    def supported_tickers(self) -> list[str]:
        return list(SUPPORTED_TICKERS.keys())

    def health_check(self) -> HealthStatus:
        try:
            from vnstock import Finance  # type: ignore
            return HealthStatus(source_name="vnstock", available=True, message="vnstock available")
        except ImportError:
            return HealthStatus(source_name="vnstock", available=False, message="vnstock not installed")

    def fetch(self, ticker: str, years: list[int]) -> pd.DataFrame:
        """Fetch all years for a ticker, using cache when available."""
        all_cached: list[pd.DataFrame] = []
        missing_years: list[int] = []

        for year in years:
            cached = _load_cache(ticker, year)
            if cached is not None:
                all_cached.append(cached)
            else:
                missing_years.append(year)

        if not missing_years:
            return pd.concat(all_cached, ignore_index=True) if all_cached else pd.DataFrame()

        # Fetch from vnstock
        logger.info(f"[vnstock] Crawling {ticker} years {missing_years}...")
        try:
            from vnstock import Finance  # type: ignore
            fin = Finance(source=DEFAULT_SOURCE, symbol=ticker, period="year")

            frames: list[pd.DataFrame] = []
            for stmt_key, method in [
                ("balance_sheet", "balance_sheet"),
                ("income_statement", "income_statement"),
                ("cash_flow", "cash_flow"),
            ]:
                try:
                    raw_df = getattr(fin, method)(period="year", lang="vi")
                    if isinstance(raw_df, pd.DataFrame) and not raw_df.empty:
                        melted = _melt_report(raw_df, ticker, stmt_key)
                        if not melted.empty:
                            frames.append(melted)
                    time.sleep(0.5)
                except SystemExit:
                    logger.warning(f"[vnstock] Rate limit hit for {ticker} {stmt_key}")
                    break
                except Exception as e:
                    logger.warning(f"[vnstock] {ticker} {stmt_key}: {e}")

            if frames:
                full_df = pd.concat(frames, ignore_index=True)
                for year in full_df["year"].unique():
                    year_slice = full_df[full_df["year"] == year].copy()
                    if not year_slice.empty:
                        _save_cache(year_slice, ticker, int(year))
                result_df = full_df[full_df["year"].isin(years)].copy()
                if all_cached:
                    result_df = pd.concat(
                        [pd.concat(all_cached), result_df], ignore_index=True
                    )
                return result_df

        except SystemExit:
            logger.warning(f"[vnstock] Rate limit for {ticker}")
        except Exception as e:
            logger.warning(f"[vnstock] Error fetching {ticker}: {e}")

        return pd.concat(all_cached, ignore_index=True) if all_cached else pd.DataFrame()

    def fetch_with_mock_fallback(
        self, ticker: str, years: list[int]
    ) -> pd.DataFrame:
        """Fetch with automatic mock fallback."""
        df = self.fetch(ticker, years)
        if df.empty:
            logger.info(f"[vnstock] Using mock data for {ticker}")
            return _generate_mock(ticker, years)
        return df

    def fetch_multiple(self, tickers: list[str], years: list[int]) -> pd.DataFrame:
        """Sequential fetch with rate-limit delays."""
        frames: list[pd.DataFrame] = []
        for i, ticker in enumerate(tickers):
            if i > 0:
                time.sleep(3.5)
            try:
                df = self.fetch(ticker, years)
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                logger.warning(f"[vnstock] {ticker}: {e}")
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def fetch_market_info(self, ticker: str) -> dict:
        """Fetch the latest available close from vnstock's quote endpoint."""
        try:
            from vnstock import Quote
            end = date.today()
            start = end - timedelta(days=10)
            history = Quote(symbol=ticker, show_log=False).history(
                start=start.isoformat(), end=end.isoformat(), interval="1D"
            )
            if history is None or history.empty:
                return {}
            close_column = next((c for c in history.columns if str(c).lower() in {"close", "close_price"}), None)
            if close_column is None:
                return {}
            last = history.dropna(subset=[close_column]).iloc[-1]
            as_of = last.get("time") or last.get("date") or end.isoformat()
            return {"current_price": float(last[close_column]), "currency": "VND", "as_of": str(as_of)}
        except Exception as exc:
            logger.warning("[vnstock] Quote fetch failed for %s: %s", ticker, exc)
            return {}


def get_cache_status() -> dict[str, dict]:
    """Return cache status for all supported tickers."""
    from datetime import datetime
    status = {}
    for symbol in SUPPORTED_TICKERS:
        files = [
            f for f in os.listdir(CACHE_DIR)
            if f.startswith(f"{symbol}_") and f.endswith(".csv")
        ]
        if not files:
            status[symbol] = {"status": "missing", "files": 0, "last_updated": None}
            continue
        mtimes = [os.path.getmtime(os.path.join(CACHE_DIR, f)) for f in files]
        oldest = min(mtimes)
        newest = max(mtimes)
        age_hours = (time.time() - oldest) / 3600
        status[symbol] = {
            "status": "fresh" if age_hours < CACHE_TTL_HOURS else "stale",
            "files": len(files),
            "last_updated": datetime.fromtimestamp(newest).isoformat(),
            "age_hours": round(age_hours, 1),
        }
    return status
