"""
etl/run_etl.py
CLI entry point for running ETL pipeline.

Usage:
  python -m etl.run_etl --source investopedia_financial
  python -m etl.run_etl --seed-only
  python -m etl.run_etl --all --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from etl.sources import SOURCES, get_source, list_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qdrant_data")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")


def load_seed_data() -> dict[str, int]:
    """Load all seed JSON files into Qdrant collections."""
    from etl.loader import load_seed_json_to_qdrant

    seed_files = {
        "financial_terms.json": ("financial_glossary", "financial_glossary"),
        "economics_theory.json": ("economics_glossary", "economics"),
        "quant_finance.json": ("quant_finance", "quant_finance"),
        "vietnam_market.json": ("vietnam_market", "vietnam_market"),
    }

    results = {}
    for filename, (collection, category) in seed_files.items():
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        if not os.path.exists(filepath):
            logger.warning(f"Seed file not found: {filepath}")
            continue

        logger.info(f"Loading seed: {filename} → {collection}")
        try:
            count = load_seed_json_to_qdrant(filepath, collection, category, QDRANT_PATH)
            results[filename] = count
            logger.info(f"  ✓ Loaded {count} entries from {filename}")
        except Exception as e:
            logger.error(f"  ✗ Failed {filename}: {e}")
            results[filename] = 0

    return results


async def run_web_etl(source_name: str, limit: int | None = None, dry_run: bool = False) -> dict:
    """Run full ETL pipeline for a web source."""
    from etl.chunker import chunk_documents
    from etl.extract import extract_from_source
    from etl.loader import load_chunks_to_qdrant
    from etl.state import changed_documents, load_state, record_documents
    from etl.transform import transform_pages

    source = get_source(source_name)
    if source is None:
        logger.error(f"Source not found: {source_name}")
        return {"error": f"Unknown source: {source_name}"}

    if limit:
        source.max_pages = limit

    start = time.time()
    stats = {"source": source_name, "collection": source.collection}

    # Extract
    logger.info(f"[ETL] EXTRACT: {source_name} ({len(source.glossary_urls)} URLs)")
    pages = await extract_from_source(source)
    stats["pages_fetched"] = len(pages)

    # Transform
    logger.info(f"[ETL] TRANSFORM: {len(pages)} pages")
    docs = transform_pages(pages, category=source.category, tags=source.tags)
    stats["documents_cleaned"] = len(docs)
    manifest = load_state()
    changed_docs = changed_documents(docs, manifest, source_name)
    stats["documents_changed"] = len(changed_docs)
    stats["documents_unchanged"] = len(docs) - len(changed_docs)

    # Chunk
    logger.info(f"[ETL] CHUNK: {len(changed_docs)} changed documents")
    chunks = chunk_documents(changed_docs)
    stats["chunks_created"] = len(chunks)

    if dry_run:
        logger.info(f"[ETL] DRY RUN — skipping load. Stats: {stats}")
        stats["loaded"] = 0
        stats["dry_run"] = True
    else:
        # Load
        logger.info(f"[ETL] LOAD: {len(chunks)} chunks → {source.collection}")
        loaded = load_chunks_to_qdrant(chunks, source.collection, QDRANT_PATH)
        stats["loaded"] = loaded
        record_documents(docs, manifest, source_name)

    elapsed = time.time() - start
    stats["elapsed_seconds"] = round(elapsed, 1)
    logger.info(f"[ETL] DONE: {source_name} in {elapsed:.1f}s | {stats}")
    return stats


async def run_all(limit: int | None = None, dry_run: bool = False) -> list[dict]:
    """Run ETL for all configured sources."""
    results = []
    for name in SOURCES:
        result = await run_web_etl(name, limit=limit, dry_run=dry_run)
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="ETL Pipeline for Knowledge Base")
    parser.add_argument("--source", type=str, help="Run ETL for a specific source")
    parser.add_argument("--all", action="store_true", help="Run ETL for all sources")
    parser.add_argument("--seed-only", action="store_true", help="Only load seed JSON data")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of pages per source")
    parser.add_argument("--dry-run", action="store_true", help="Extract+transform only, skip loading")
    parser.add_argument("--list", action="store_true", help="List available sources")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable sources:")
        for s in list_sources():
            print(f"  {s['name']:30s} → {s['collection']:25s} ({s['urls_count']} URLs, max {s['max_pages']})")
        return

    if args.seed_only:
        print("\n=== Loading Seed Data ===")
        results = load_seed_data()
        print(f"\nResults: {results}")
        return

    if args.source:
        print(f"\n=== Running ETL: {args.source} ===")
        # Load seed data first
        load_seed_data()
        result = asyncio.run(run_web_etl(args.source, limit=args.limit, dry_run=args.dry_run))
        print(f"\nResult: {result}")
        return

    if args.all:
        print("\n=== Running ETL: ALL sources ===")
        load_seed_data()
        results = asyncio.run(run_all(limit=args.limit, dry_run=args.dry_run))
        print(f"\nResults: {results}")
        return

    # Default: just seed data
    print("\n=== Loading Seed Data (default) ===")
    print("Use --source NAME or --all to run web ETL")
    print("Use --list to see available sources\n")
    results = load_seed_data()
    print(f"\nResults: {results}")


if __name__ == "__main__":
    main()
