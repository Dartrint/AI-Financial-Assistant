"""
market_data/yahoo_source.py
Yahoo Finance data source via yfinance.

Provides: price history, financial statements, dividends, market cap.
Maps Vietnam tickers to Yahoo format (VCB → VCB.VN).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from config import SUPPORTED_TICKERS
from market_data.base import DataSource, HealthStatus

logger = logging.getLogger(__name__)

# Yahoo Finance ticker mapping for Vietnamese stocks
YAHOO_SUFFIX = ".VN"

# Map Yahoo Finance line item names to our normalized keys
YAHOO_LINE_ITEM_MAP = {
    # Income Statement
    "Total Revenue": "doanh_thu_thuan",
    "Net Income": "loi_nhuan_sau_thue",
    "Gross Profit": "loi_nhuan_gop",
    "Operating Income": "loi_nhuan_thuan_hdkd",
    "Pretax Income": "loi_nhuan_truoc_thue",
    "Net Income Common Stockholders": "loi_nhuan_sau_thue_cong_ty_me",
    "Cost Of Revenue": "gia_von_hang_ban",
    "Operating Expense": "chi_phi_hoat_dong",
    # Balance Sheet
    "Total Assets": "tong_tai_san",
    "Total Liabilities Net Minority Interest": "no_phai_tra",
    "Stockholders Equity": "von_chu_so_huu",
    "Current Assets": "tai_san_ngan_han",
    "Current Liabilities": "no_ngan_han",
    "Total Non Current Assets": "tai_san_dai_han",
    "Total Non Current Liabilities Net Minority Interest": "no_dai_han",
    "Inventory": "hang_ton_kho",
    "Cash And Cash Equivalents": "tien_va_tuong_duong_tien",
    # Cash Flow
    "Operating Cash Flow": "luu_chuyen_tien_kinh_doanh",
    "Investing Cash Flow": "luu_chuyen_tien_dau_tu",
    "Financing Cash Flow": "luu_chuyen_tien_tai_chinh",
}

STATEMENT_TYPE_MAP = {
    "income_stmt": "ket_qua_kinh_doanh",
    "balance_sheet": "bang_can_doi_ke_toan",
    "cashflow": "luu_chuyen_tien_te",
}


class YahooFinanceSource(DataSource):
    """Yahoo Finance data source for global + Vietnam market data."""

    @property
    def name(self) -> str:
        return "yahoo_finance"

    def supported_tickers(self) -> list[str]:
        return list(SUPPORTED_TICKERS.keys())

    def health_check(self) -> HealthStatus:
        try:
            import yfinance as yf  # type: ignore
            ticker = yf.Ticker("VCB.VN")
            info = ticker.info
            if info and info.get("symbol"):
                return HealthStatus(
                    source_name="yahoo_finance", available=True,
                    message="Yahoo Finance API reachable",
                )
            return HealthStatus(
                source_name="yahoo_finance", available=True,
                message="Yahoo Finance available (limited data)",
            )
        except ImportError:
            return HealthStatus(
                source_name="yahoo_finance", available=False,
                message="yfinance not installed",
            )
        except Exception as e:
            return HealthStatus(
                source_name="yahoo_finance", available=False,
                message=f"Yahoo Finance error: {str(e)[:100]}",
            )

    def _to_yahoo_ticker(self, ticker: str) -> str:
        """Convert VN ticker to Yahoo format."""
        return f"{ticker}{YAHOO_SUFFIX}"

    def _melt_statement(
        self,
        df: pd.DataFrame,
        ticker: str,
        statement_type: str,
    ) -> pd.DataFrame:
        """Convert yfinance statement (columns=dates, rows=items) to long format."""
        if df is None or df.empty:
            return pd.DataFrame()

        rows = []
        stmt_normalized = STATEMENT_TYPE_MAP.get(statement_type, statement_type)

        for item_name in df.index:
            normalized = YAHOO_LINE_ITEM_MAP.get(str(item_name))
            for col in df.columns:
                val = df.loc[item_name, col]
                if pd.isna(val):
                    continue
                try:
                    year = col.year if hasattr(col, "year") else int(str(col)[:4])
                    float_val = float(val)
                except (ValueError, TypeError, AttributeError):
                    continue

                rows.append({
                    "company_code": ticker,
                    "company_name": SUPPORTED_TICKERS.get(ticker, ticker),
                    "year": year,
                    "statement_type": stmt_normalized,
                    "line_item": str(item_name),
                    "line_item_normalized": normalized,
                    "value": float_val,
                    "unit": "VND",
                    "source_file": f"yahoo:{ticker}:{statement_type}",
                    "source_page": f"Yahoo Finance - {statement_type} {year}",
                })

        return pd.DataFrame(rows)

    def fetch(self, ticker: str, years: list[int]) -> pd.DataFrame:
        """Fetch financial statements from Yahoo Finance."""
        try:
            import yfinance as yf  # type: ignore
        except ImportError:
            logger.warning("[yahoo] yfinance not installed")
            return pd.DataFrame()

        yahoo_ticker = self._to_yahoo_ticker(ticker)
        logger.info(f"[yahoo] Fetching {yahoo_ticker}...")

        try:
            stock = yf.Ticker(yahoo_ticker)
            frames: list[pd.DataFrame] = []

            # Fetch annual financial statements
            for stmt_attr, stmt_type in [
                ("income_stmt", "income_stmt"),
                ("balance_sheet", "balance_sheet"),
                ("cashflow", "cashflow"),
            ]:
                try:
                    raw_df = getattr(stock, stmt_attr, None)
                    if raw_df is not None and not raw_df.empty:
                        melted = self._melt_statement(raw_df, ticker, stmt_type)
                        if not melted.empty:
                            frames.append(melted)
                except Exception as e:
                    logger.warning(f"[yahoo] {ticker} {stmt_type}: {e}")

            if frames:
                combined = pd.concat(frames, ignore_index=True)
                # Filter to requested years
                combined = combined[combined["year"].isin(years)].copy()
                logger.info(f"[yahoo] {ticker}: {len(combined)} rows")
                return combined

        except Exception as e:
            logger.warning(f"[yahoo] Error fetching {ticker}: {e}")

        return pd.DataFrame()

    def fetch_price_history(
        self, ticker: str, period: str = "5y"
    ) -> pd.DataFrame:
        """Fetch historical price data (not part of standard DataSource interface)."""
        try:
            import yfinance as yf  # type: ignore
            yahoo_ticker = self._to_yahoo_ticker(ticker)
            stock = yf.Ticker(yahoo_ticker)
            hist = stock.history(period=period)
            if not hist.empty:
                hist["ticker"] = ticker
            return hist
        except Exception as e:
            logger.warning(f"[yahoo] Price history error for {ticker}: {e}")
            return pd.DataFrame()

    def fetch_market_info(self, ticker: str) -> dict:
        """Fetch market info (market cap, P/E, etc.)."""
        try:
            import yfinance as yf  # type: ignore
            yahoo_ticker = self._to_yahoo_ticker(ticker)
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info or {}
            return {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "pb_ratio": info.get("priceToBook"),
                "dividend_yield": info.get("dividendYield"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "current_price": info.get("currentPrice"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "currency": info.get("currency", "VND"),
                "market_state": info.get("marketState"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"[yahoo] Market info error for {ticker}: {e}")
            return {}
