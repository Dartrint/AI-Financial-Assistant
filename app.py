"""
app.py
Multi-Layer AI Financial Assistant — FastAPI Application.

Architecture:
  Market Data → Knowledge → Retrieval → LLM → Tools → Dashboard

Endpoints:
  GET  /                       - Dashboard UI
  POST /ask                    - Chat query endpoint
  GET  /api/overview           - Portfolio overview
  GET  /api/ticker/{symbol}    - Ticker detail
  GET  /api/crawl-status       - Cache status
  GET  /api/sources            - Data sources status
  GET  /api/llm/status         - LLM providers status
  GET  /api/tools              - Available tools
  GET  /api/knowledge/search   - Knowledge base search
  GET  /api/architecture       - Full architecture status
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.requests import Request

from agent import FinancialAgent
from config import SUPPORTED_TICKERS

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOLS = list(SUPPORTED_TICKERS.keys())
YEARS = [int(y) for y in os.getenv("SUPPORTED_YEARS", "2020,2021,2022,2023,2024").split(",") if y.strip()]

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

_jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)


# ---------------------------------------------------------------------------
# App State
# ---------------------------------------------------------------------------

class AppState:
    dataset: pd.DataFrame = pd.DataFrame()
    agent: FinancialAgent | None = None
    is_crawling: bool = False
    crawl_started_at: float = 0.0
    history: list[dict[str, Any]] = []
    aggregator = None
    llm_router = None
    retriever = None
    knowledge_base = None
    tool_registry = None
    market_store = None

state = AppState()


# ---------------------------------------------------------------------------
# Background init — crawl data + build indices
# ---------------------------------------------------------------------------

async def _background_init(symbols: list[str], years: list[int]) -> None:
    """Initialize all layers in background on startup."""
    if state.is_crawling:
        return
    state.is_crawling = True
    state.crawl_started_at = time.time()

    try:
        # 1. Market Data Layer
        logger.info("[STARTUP] Initializing Market Data Layer...")
        from market_data.aggregator import DataAggregator
        from market_data.duckdb_store import DuckDBStore
        state.aggregator = DataAggregator()
        state.market_store = DuckDBStore()
        df = await asyncio.to_thread(
            state.aggregator.fetch_multiple, symbols, years, False
        )
        if not df.empty:
            # Persist annual statements only. Quotes and macro observations stay
            # in their live-data tools and are never copied into the RAG store.
            state.market_store.upsert(df)
            state.dataset = state.market_store.get_all()
            logger.info(f"[STARTUP] Loaded {len(df)} records for {df['company_code'].nunique()} companies")
        else:
            # A transient provider outage should not hide the last verified
            # annual statements already persisted in DuckDB.
            state.dataset = state.market_store.get_all()

        # 2. Knowledge Layer
        logger.info("[STARTUP] Initializing Knowledge Layer...")
        from knowledge.loader import KnowledgeBase
        state.knowledge_base = KnowledgeBase()
        state.knowledge_base.load()
        kb_stats = state.knowledge_base.stats()
        logger.info(f"[STARTUP] Knowledge: {kb_stats['total_documents']} documents")

        # 3. LLM Layer
        logger.info("[STARTUP] Initializing LLM Layer...")
        from llm.router import LLMRouter
        state.llm_router = LLMRouter()
        llm_status = state.llm_router.status()
        logger.info(f"[STARTUP] LLM: {llm_status}")

        # 4. Retrieval Layer
        logger.info("[STARTUP] Initializing Retrieval Layer...")
        from retrieval.hybrid_retriever import HybridRetriever
        state.retriever = HybridRetriever(
            knowledge_base=state.knowledge_base,
            use_reranker=True,
            llm_router=state.llm_router,
        )
        await asyncio.to_thread(state.retriever.build_index)
        logger.info(f"[STARTUP] Retrieval: {state.retriever.stats()}")

        # 5. Tools Layer
        logger.info("[STARTUP] Initializing Tools Layer...")
        from tools.base import ToolRegistry
        from tools.stock_analysis import StockAnalysisTool
        from tools.economic_analysis import EconomicAnalysisTool
        from tools.explain_concept import ExplainConceptTool
        from tools.portfolio_metrics import PortfolioMetricsTool
        from tools.market_data import MarketDataTool
        state.tool_registry = ToolRegistry()
        state.tool_registry.register(StockAnalysisTool())
        state.tool_registry.register(EconomicAnalysisTool())
        state.tool_registry.register(ExplainConceptTool())
        state.tool_registry.register(PortfolioMetricsTool())
        state.tool_registry.register(MarketDataTool())

        # 6. Agent (orchestrator)
        state.agent = FinancialAgent(
            dataset=state.dataset,
            llm_router=state.llm_router,
            retriever=state.retriever,
            tool_registry=state.tool_registry,
            aggregator=state.aggregator,
        )
        logger.info("[STARTUP] Agent initialized — all layers ready!")

    except Exception as e:
        logger.error(f"[STARTUP] Error: {e}", exc_info=True)
        # Fallback agent
        state.agent = FinancialAgent(dataset=state.dataset)
    finally:
        state.is_crawling = False
        elapsed = time.time() - state.crawl_started_at
        logger.info(f"[STARTUP] Completed in {elapsed:.1f}s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_background_init(SYMBOLS, YEARS))
    yield

app = FastAPI(title="AI Financial Assistant", lifespan=lifespan)

@app.middleware("http")
async def utf8_middleware(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # The template consumes objects with ``symbol`` and ``name``.  Keep this
    # view-model conversion at the boundary instead of leaking config's raw
    # ``dict[str, str]`` shape into Jinja.
    ticker_items = [
        {"symbol": symbol, "name": name}
        for symbol, name in SUPPORTED_TICKERS.items()
    ]
    tpl = _jinja_env.get_template("index.html")
    html = tpl.render(symbols=SYMBOLS, tickers=ticker_items)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@app.post("/ask")
async def ask(question: str = Form(...)):
    if state.agent is None:
        state.agent = FinancialAgent(dataset=state.dataset)

    start = time.time()
    result = await asyncio.to_thread(state.agent.answer, question)
    elapsed = round((time.time() - start) * 1000)

    state.history.append({
        "question": question,
        "answer": result.get("answer", ""),
        "intent": result.get("intent"),
        "tool_used": result.get("tool_used", "none"),
        "llm_provider": result.get("llm_provider", "none"),
        "elapsed_ms": elapsed,
    })

    return JSONResponse({
        **result,
        "elapsed_ms": elapsed,
    })


# ---------------------------------------------------------------------------
# Data API
# ---------------------------------------------------------------------------

@app.get("/api/overview")
async def api_overview():
    df = state.dataset
    if df.empty:
        return {"symbols": [], "total_rows": 0, "years": [], "is_crawling": state.is_crawling}

    symbols = sorted(df["company_code"].unique().tolist())
    years = sorted(df["year"].dropna().astype(int).unique().tolist())

    return {
        "symbols": symbols,
        "total_rows": len(df),
        "years": years,
        "is_crawling": state.is_crawling,
    }


@app.get("/api/ticker/{symbol}")
async def api_ticker(symbol: str):
    symbol = symbol.upper()
    df = state.dataset
    if df.empty or symbol not in df["company_code"].values:
        raise HTTPException(404, detail=f"No data for {symbol}")

    sym_df = df[df["company_code"] == symbol]
    latest_year = int(sym_df["year"].max())
    latest = sym_df[sym_df["year"] == latest_year]

    metrics = {}
    for _, row in latest.iterrows():
        key = row.get("line_item_normalized") or row.get("line_item")
        if key:
            metrics[key] = {"value": float(row["value"]), "unit": row.get("unit", "VND")}

    years_data = {}
    for year in sorted(sym_df["year"].unique()):
        year_df = sym_df[sym_df["year"] == year]
        years_data[int(year)] = {
            row.get("line_item_normalized", row.get("line_item")): float(row["value"])
            for _, row in year_df.iterrows()
        }

    return {
        "symbol": symbol,
        "name": SUPPORTED_TICKERS.get(symbol, symbol),
        "latest_year": latest_year,
        "metrics": metrics,
        "years_data": years_data,
    }


@app.get("/api/crawl-status")
async def api_crawl_status():
    from market_data.vnstock_source import get_cache_status
    cache = get_cache_status()
    return {
        "is_crawling": state.is_crawling,
        "cache": cache,
        "dataset": {
            sym: {"in_memory": True, "rows": len(state.dataset[state.dataset["company_code"] == sym])}
            for sym in state.dataset["company_code"].unique()
        } if not state.dataset.empty else {},
    }


# ---------------------------------------------------------------------------
# Architecture Status APIs
# ---------------------------------------------------------------------------

@app.get("/api/sources")
async def api_sources():
    """Data sources health status."""
    if state.aggregator:
        health = state.aggregator.health_check_all()
        return {
            "sources": {
                name: {"available": h.available, "message": h.message}
                for name, h in health.items()
            },
            "priority": state.aggregator.priority,
        }
    return {"sources": {}, "priority": []}


@app.get("/api/llm/status")
async def api_llm_status():
    """LLM providers status."""
    if state.llm_router:
        return state.llm_router.status()
    return {"providers": {}, "active": None, "priority": []}


@app.get("/api/tools")
async def api_tools():
    """Available tools."""
    if state.tool_registry:
        return {"tools": state.tool_registry.list_tools()}
    return {"tools": []}


@app.get("/api/knowledge/search")
async def api_knowledge_search(q: str = ""):
    """Search knowledge base."""
    if not q or not state.retriever:
        if state.knowledge_base:
            return {"results": [], "stats": state.knowledge_base.stats()}
        return {"results": [], "stats": {}}

    results = state.retriever.search(q, top_k=5)
    return {
        "results": [
            {
                "title": r.document.title,
                "content": r.document.content,
                "category": r.document.category,
                "score": round(r.score, 4),
                "source": r.source,
                "metadata": r.document.metadata,
            }
            for r in results
        ],
        "stats": state.knowledge_base.stats() if state.knowledge_base else {},
    }


@app.get("/api/architecture")
async def api_architecture():
    """Full architecture status for dashboard."""
    layers = {
        "market_data": {
            "name": "Market Data Layer",
            "status": "active" if state.aggregator else "initializing",
            "sources": {},
            "store": state.market_store.stats() if state.market_store else {},
        },
        "knowledge": {
            "name": "Knowledge Layer",
            "status": "active" if state.knowledge_base and state.knowledge_base.stats().get("loaded") else "initializing",
            "stats": state.knowledge_base.stats() if state.knowledge_base else {},
        },
        "retrieval": {
            "name": "Retrieval Layer",
            "status": "active" if state.retriever and state.retriever.is_indexed else "initializing",
            "stats": state.retriever.stats() if state.retriever else {},
        },
        "llm": {
            "name": "LLM Layer",
            "status": "active" if state.llm_router else "initializing",
            "providers": state.llm_router.status() if state.llm_router else {},
        },
        "tools": {
            "name": "Tools Layer",
            "status": "active" if state.tool_registry else "initializing",
            "tools": state.tool_registry.list_tools() if state.tool_registry else [],
        },
    }

    if state.aggregator:
        health = state.aggregator.health_check_all()
        layers["market_data"]["sources"] = {
            name: {"available": h.available, "message": h.message}
            for name, h in health.items()
        }

    all_active = all(l["status"] == "active" for l in layers.values())

    return {
        "status": "ready" if all_active else "initializing",
        "layers": layers,
        "dataset_rows": len(state.dataset),
        "is_crawling": state.is_crawling,
    }
