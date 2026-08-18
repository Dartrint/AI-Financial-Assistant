"""
market_data/duckdb_store.py
DuckDB storage backend for market data.
Replaces CSV-based caching with structured SQL storage.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market.duckdb")


class DuckDBStore:
    """Persistent DuckDB store for financial market data."""

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._ensure_table()

    def _connect(self):
        import duckdb
        return duckdb.connect(self._db_path)

    def _ensure_table(self) -> None:
        con = self._connect()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS financial_data (
                    company_code VARCHAR,
                    company_name VARCHAR,
                    year INTEGER,
                    statement_type VARCHAR,
                    line_item VARCHAR,
                    line_item_normalized VARCHAR,
                    value DOUBLE,
                    unit VARCHAR DEFAULT 'VND',
                    source_file VARCHAR,
                    source_page VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS idx_company_year
                ON financial_data (company_code, year)
            """)
            logger.info(f"[DuckDB] Table ensured at {self._db_path}")
        finally:
            con.close()

    def upsert(self, df: pd.DataFrame) -> int:
        """Insert/update data. Deduplicates by (company_code, year, line_item_normalized, statement_type)."""
        if df.empty:
            return 0

        con = self._connect()
        try:
            df = df.drop_duplicates(
                subset=["company_code", "year", "line_item_normalized", "statement_type"],
                keep="first"
            )
            # Delete existing entries for same company/year/metric combos
            for _, row in df[["company_code", "year"]].drop_duplicates().iterrows():
                con.execute(
                    "DELETE FROM financial_data WHERE company_code = ? AND year = ?",
                    [row["company_code"], int(row["year"])]
                )
            # Insert new data
            required_cols = [
                "company_code", "company_name", "year", "statement_type",
                "line_item", "line_item_normalized", "value", "unit",
                "source_file", "source_page",
            ]
            for col in required_cols:
                if col not in df.columns:
                    df[col] = ""
            insert_df = df[required_cols].copy()
            insert_df["created_at"] = datetime.now()

            con.execute("INSERT INTO financial_data SELECT * FROM insert_df")
            count = len(insert_df)
            logger.info(f"[DuckDB] Upserted {count} rows")
            return count
        finally:
            con.close()

    def query(
        self,
        tickers: Optional[list[str]] = None,
        years: Optional[list[int]] = None,
        metrics: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Query market data with optional filters."""
        con = self._connect()
        try:
            conditions = []
            params = []
            if tickers:
                placeholders = ",".join(["?"] * len(tickers))
                conditions.append(f"company_code IN ({placeholders})")
                params.extend(tickers)
            if years:
                placeholders = ",".join(["?"] * len(years))
                conditions.append(f"year IN ({placeholders})")
                params.extend(years)
            if metrics:
                placeholders = ",".join(["?"] * len(metrics))
                conditions.append(f"line_item_normalized IN ({placeholders})")
                params.extend(metrics)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            sql = f"SELECT * FROM financial_data {where} ORDER BY company_code, year"
            return con.execute(sql, params).fetchdf()
        finally:
            con.close()

    def get_all(self) -> pd.DataFrame:
        """Get all data."""
        return self.query()

    def stats(self) -> dict:
        """Return database statistics."""
        con = self._connect()
        try:
            total = con.execute("SELECT COUNT(*) FROM financial_data").fetchone()[0]
            companies = con.execute("SELECT COUNT(DISTINCT company_code) FROM financial_data").fetchone()[0]
            years = con.execute("SELECT DISTINCT year FROM financial_data ORDER BY year").fetchdf()["year"].tolist()
            return {
                "total_rows": total,
                "companies": companies,
                "years": years,
                "db_path": self._db_path,
            }
        finally:
            con.close()
