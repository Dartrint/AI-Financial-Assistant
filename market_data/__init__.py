"""
Market Data Layer — Multi-source financial data pipeline.

Sources:
  - vnstock: Vietnam stock market (VCI/TCBS APIs)
  - EcoData: Structured financial data API
  - Yahoo Finance: Global market data (yfinance)
"""

from market_data.aggregator import DataAggregator
from market_data.base import DataSource, FinancialRecord

__all__ = ["DataAggregator", "DataSource", "FinancialRecord"]
