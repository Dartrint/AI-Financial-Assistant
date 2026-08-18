"""
etl/sources.py
Source configurations for knowledge ETL pipeline.
Each source defines URLs, collection target, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    """Configuration for a single knowledge source."""
    name: str
    base_url: str
    collection: str
    category: str
    tags: list[str] = field(default_factory=list)
    glossary_urls: list[str] = field(default_factory=list)
    sitemap_url: str | None = None
    url_pattern: str | None = None  # Regex filter for discovered URLs
    max_pages: int = 200
    delay_seconds: float = 1.0


# ---------------------------------------------------------------------------
# Pre-configured sources
# ---------------------------------------------------------------------------

SOURCES: dict[str, SourceConfig] = {
    "investopedia_financial": SourceConfig(
        name="investopedia_financial",
        base_url="https://www.investopedia.com",
        collection="financial_glossary",
        category="financial_glossary",
        tags=["investing", "finance", "glossary"],
        glossary_urls=[
            "https://www.investopedia.com/financial-term-dictionary-4769738",
            "https://www.investopedia.com/terms/r/roe.asp",
            "https://www.investopedia.com/terms/r/roa.asp",
            "https://www.investopedia.com/terms/p/pe-ratio.asp",
            "https://www.investopedia.com/terms/e/eps.asp",
            "https://www.investopedia.com/terms/d/dcf.asp",
            "https://www.investopedia.com/terms/c/capm.asp",
            "https://www.investopedia.com/terms/s/sharperatio.asp",
            "https://www.investopedia.com/terms/v/var.asp",
            "https://www.investopedia.com/terms/w/wacc.asp",
            "https://www.investopedia.com/terms/b/beta.asp",
            "https://www.investopedia.com/terms/a/alpha.asp",
            "https://www.investopedia.com/terms/e/ebitda.asp",
            "https://www.investopedia.com/terms/f/freecashflow.asp",
            "https://www.investopedia.com/terms/d/dividendyield.asp",
            "https://www.investopedia.com/terms/m/marketcapitalization.asp",
            "https://www.investopedia.com/terms/b/balancesheet.asp",
            "https://www.investopedia.com/terms/i/incomestatement.asp",
            "https://www.investopedia.com/terms/c/cashflowstatement.asp",
            "https://www.investopedia.com/terms/n/npv.asp",
            "https://www.investopedia.com/terms/i/irr.asp",
            "https://www.investopedia.com/terms/d/debtequityratio.asp",
            "https://www.investopedia.com/terms/c/currentratio.asp",
            "https://www.investopedia.com/terms/g/grossprofit.asp",
            "https://www.investopedia.com/terms/n/netincome.asp",
        ],
        max_pages=100,
        delay_seconds=2.0,
    ),
    "sec_glossary": SourceConfig(
        name="sec_glossary",
        base_url="https://www.sec.gov",
        collection="financial_glossary",
        category="financial_glossary",
        tags=["sec", "regulation", "glossary"],
        glossary_urls=[
            "https://www.sec.gov/resources-for-investors/investor-alerts-bulletins",
        ],
        max_pages=50,
        delay_seconds=2.0,
    ),
    "imf_economics": SourceConfig(
        name="imf_economics",
        base_url="https://www.imf.org",
        collection="economics_glossary",
        category="economics",
        tags=["economics", "macro", "imf"],
        glossary_urls=[
            "https://www.imf.org/en/About/Factsheets",
        ],
        max_pages=50,
        delay_seconds=2.0,
    ),
    "quantconnect_docs": SourceConfig(
        name="quantconnect_docs",
        base_url="https://www.quantconnect.com",
        collection="quant_finance",
        category="quant_finance",
        tags=["quantitative", "algorithms", "trading"],
        glossary_urls=[
            "https://www.quantconnect.com/docs/v2",
        ],
        max_pages=100,
        delay_seconds=1.5,
    ),
    "cfi_articles": SourceConfig(
        name="cfi_articles",
        base_url="https://corporatefinanceinstitute.com",
        collection="financial_glossary",
        category="financial_glossary",
        tags=["cfi", "finance", "education"],
        glossary_urls=[
            "https://corporatefinanceinstitute.com/resources/accounting/",
            "https://corporatefinanceinstitute.com/resources/valuation/",
            "https://corporatefinanceinstitute.com/resources/financial-modeling/",
        ],
        max_pages=80,
        delay_seconds=2.0,
    ),
    "vietnam_market": SourceConfig(
        name="vietnam_market",
        base_url="https://vietstock.vn",
        collection="vietnam_market",
        category="vietnam_market",
        tags=["vietnam", "stock_market", "vietnamese"],
        glossary_urls=[
            "https://finance.vietstock.vn/",
        ],
        max_pages=50,
        delay_seconds=2.0,
    ),
}


def get_source(name: str) -> SourceConfig | None:
    return SOURCES.get(name)


def list_sources() -> list[dict]:
    return [
        {
            "name": s.name,
            "collection": s.collection,
            "category": s.category,
            "urls_count": len(s.glossary_urls),
            "max_pages": s.max_pages,
        }
        for s in SOURCES.values()
    ]
