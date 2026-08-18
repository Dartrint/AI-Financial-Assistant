"""
market_data/base.py
Abstract interface for all data sources + common data structures.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FinancialRecord:
    """Standardized financial data record (one line item for one company-year)."""
    company_code: str
    company_name: str
    year: int
    statement_type: str  # ket_qua_kinh_doanh | bang_can_doi_ke_toan | luu_chuyen_tien_te
    line_item: str  # Original name from source
    line_item_normalized: str | None  # Normalized key (e.g. doanh_thu_thuan)
    value: float
    unit: str = "VND"
    source_file: str = ""
    source_page: str = ""


@dataclass
class HealthStatus:
    """Health check result for a data source."""
    source_name: str
    available: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class DataSource(ABC):
    """Abstract base for all market data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this data source."""
        ...

    @abstractmethod
    def fetch(self, ticker: str, years: list[int]) -> pd.DataFrame:
        """
        Fetch financial data for a single ticker and set of years.

        Must return a DataFrame with columns:
            company_code, company_name, year, statement_type,
            line_item, line_item_normalized, value, unit,
            source_file, source_page
        """
        ...

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Check if this data source is available and functional."""
        ...

    def supported_tickers(self) -> list[str]:
        """Return list of supported tickers (empty = supports all)."""
        return []

    def fetch_multiple(self, tickers: list[str], years: list[int]) -> pd.DataFrame:
        """Fetch data for multiple tickers. Default: sequential fetch."""
        frames: list[pd.DataFrame] = []
        for ticker in tickers:
            try:
                df = self.fetch(ticker, years)
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to fetch {ticker}: {e}")
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
