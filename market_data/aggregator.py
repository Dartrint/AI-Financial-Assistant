"""
market_data/aggregator.py
Multi-source data aggregator with priority-based fallback.

Orchestrates vnstock, EcoData, and Yahoo Finance sources.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import pandas as pd

from market_data.base import DataSource, HealthStatus

logger = logging.getLogger(__name__)


class DataAggregator:
    """
    Orchestrate multiple data sources with priority + fallback.

    Default priority: vnstock → ecodata → yahoo_finance
    Configurable via DATA_SOURCE_PRIORITY env var.
    """

    def __init__(self, sources: Optional[list[DataSource]] = None):
        if sources is not None:
            self._sources = {s.name: s for s in sources}
        else:
            self._sources = {}
            self._init_default_sources()

        # Priority order from env or default
        priority_str = os.getenv("DATA_SOURCE_PRIORITY", "vnstock,yahoo_finance,ecodata")
        self._priority = [s.strip() for s in priority_str.split(",") if s.strip()]

    def _init_default_sources(self) -> None:
        """Initialize all available data sources."""
        try:
            from market_data.vnstock_source import VnstockSource
            self._sources["vnstock"] = VnstockSource()
        except Exception as e:
            logger.warning(f"[aggregator] Failed to init vnstock: {e}")

        try:
            from market_data.ecodata_source import EcoDataSource
            self._sources["ecodata"] = EcoDataSource()
        except Exception as e:
            logger.warning(f"[aggregator] Failed to init ecodata: {e}")

        try:
            from market_data.yahoo_source import YahooFinanceSource
            self._sources["yahoo_finance"] = YahooFinanceSource()
        except Exception as e:
            logger.warning(f"[aggregator] Failed to init yahoo: {e}")

    @property
    def sources(self) -> dict[str, DataSource]:
        return self._sources

    @property
    def priority(self) -> list[str]:
        return self._priority

    def get_source(self, name: str) -> Optional[DataSource]:
        return self._sources.get(name)

    def health_check_all(self) -> dict[str, HealthStatus]:
        """Run health check on all registered sources."""
        results = {}
        for name, source in self._sources.items():
            try:
                results[name] = source.health_check()
            except Exception as e:
                results[name] = HealthStatus(
                    source_name=name, available=False, message=str(e)
                )
        return results

    def fetch(
        self,
        ticker: str,
        years: list[int],
        preferred_source: Optional[str] = None,
        use_mock_fallback: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch data using priority-based source selection with fallback.

        1. Try preferred_source (if specified)
        2. Try each source in priority order
        3. Use deterministic mock data only when an explicit test caller opts in
        """
        # Determine source order
        if preferred_source and preferred_source in self._sources:
            order = [preferred_source] + [
                s for s in self._priority if s != preferred_source
            ]
        else:
            order = list(self._priority)

        # Try each source
        for source_name in order:
            source = self._sources.get(source_name)
            if source is None:
                continue
            try:
                df = source.fetch(ticker, years)
                if not df.empty:
                    logger.info(
                        f"[aggregator] {ticker}: got {len(df)} rows from {source_name}"
                    )
                    return df
            except Exception as e:
                logger.warning(f"[aggregator] {source_name} failed for {ticker}: {e}")

        # Mock fallback
        if use_mock_fallback:
            logger.info(f"[aggregator] All sources failed for {ticker}, using mock")
            try:
                from market_data.vnstock_source import _generate_mock
                return _generate_mock(ticker, years)
            except Exception:
                pass

        logger.error(f"[aggregator] No data for {ticker} from any source")
        return pd.DataFrame()

    def fetch_multiple(
        self,
        tickers: list[str],
        years: list[int],
        use_mock_fallback: bool = False,
    ) -> pd.DataFrame:
        """Fetch data for multiple tickers with smart batching."""
        frames: list[pd.DataFrame] = []

        for i, ticker in enumerate(tickers):
            if i > 0:
                time.sleep(1.0)  # Small delay between tickers
            df = self.fetch(ticker, years, use_mock_fallback=use_mock_fallback)
            if not df.empty:
                frames.append(df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def fetch_price_history(
        self, ticker: str, period: str = "5y"
    ) -> pd.DataFrame:
        """Fetch price history (Yahoo Finance specific)."""
        yahoo = self._sources.get("yahoo_finance")
        if yahoo is not None:
            try:
                from market_data.yahoo_source import YahooFinanceSource
                if isinstance(yahoo, YahooFinanceSource):
                    return yahoo.fetch_price_history(ticker, period)
            except Exception as e:
                logger.warning(f"[aggregator] Price history error: {e}")
        return pd.DataFrame()

    def fetch_market_info(self, ticker: str) -> dict:
        """Fetch a quote and valuation fields from sources in priority order.

        Values are merged instead of selecting one all-or-nothing source: for
        example vnstock can provide a local closing price while Yahoo supplies
        P/E/P/B. The first source wins for each field and provenance is kept.
        """
        merged: dict = {}
        providers: list[str] = []
        for source_name in self._priority:
            source = self._sources.get(source_name)
            fetcher = getattr(source, "fetch_market_info", None)
            if not callable(fetcher):
                continue
            try:
                info = fetcher(ticker) or {}
                if not info:
                    continue
                providers.append(source_name)
                for key, value in info.items():
                    if value is not None and key not in merged:
                        merged[key] = value
            except Exception as exc:
                logger.warning("[aggregator] %s market info error: %s", source_name, exc)
        if providers:
            merged["data_sources"] = providers
        return merged

    def fetch_macro(self, indicator: str) -> dict:
        """Fetch a latest macro observation from a configured provider."""
        order = ["ecodata"] + [name for name in self._priority if name != "ecodata"]
        for source_name in order:
            source = self._sources.get(source_name)
            fetcher = getattr(source, "fetch_macro", None)
            if not callable(fetcher):
                continue
            try:
                result = fetcher(indicator)
                if result:
                    return result
            except Exception as exc:
                logger.warning("[aggregator] %s macro fetch failed: %s", source_name, exc)
        return {}
