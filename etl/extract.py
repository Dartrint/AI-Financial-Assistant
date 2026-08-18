"""
etl/extract.py
Extract phase — URL discovery and page fetching.
Uses httpx for async fetching, sitemap parsing, and rate limiting.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from etl.sources import SourceConfig

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; FinancialKnowledgeBot/1.0; "
    "+https://github.com/ai-financial-assistant)"
)
DEFAULT_TIMEOUT = 30
MAX_CONCURRENT = 5


@dataclass
class FetchedPage:
    """A fetched web page."""
    url: str
    html: str
    status_code: int
    content_type: str = ""


async def discover_urls_from_sitemap(sitemap_url: str, pattern: str | None = None) -> list[str]:
    """Parse sitemap.xml to discover page URLs."""
    urls = []
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(sitemap_url)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Handle sitemap index (links to other sitemaps)
            for sitemap in root.findall(".//s:sitemap/s:loc", ns):
                sub_urls = await discover_urls_from_sitemap(sitemap.text, pattern)
                urls.extend(sub_urls)

            # Handle regular sitemap
            for url_elem in root.findall(".//s:url/s:loc", ns):
                url = url_elem.text.strip()
                if pattern and not re.search(pattern, url):
                    continue
                urls.append(url)

    except Exception as e:
        logger.warning(f"[ETL/extract] Sitemap error {sitemap_url}: {e}")

    logger.info(f"[ETL/extract] Discovered {len(urls)} URLs from sitemap")
    return urls


async def fetch_page(url: str, client: httpx.AsyncClient) -> FetchedPage | None:
    """Fetch a single page with error handling."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None
        return FetchedPage(
            url=url,
            html=resp.text,
            status_code=resp.status_code,
            content_type=content_type,
        )
    except httpx.HTTPStatusError as e:
        logger.warning(f"[ETL/extract] HTTP {e.response.status_code}: {url}")
    except Exception as e:
        logger.warning(f"[ETL/extract] Fetch error {url}: {type(e).__name__}: {e}")
    return None


async def fetch_pages(
    urls: list[str],
    delay_seconds: float = 1.0,
    max_concurrent: int = MAX_CONCURRENT,
) -> list[FetchedPage]:
    """Fetch multiple pages with rate limiting and concurrency control."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[FetchedPage] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        async def fetch_with_limit(url: str) -> FetchedPage | None:
            async with semaphore:
                result = await fetch_page(url, client)
                await asyncio.sleep(delay_seconds)
                return result

        tasks = [fetch_with_limit(url) for url in urls]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        for item in fetched:
            if isinstance(item, FetchedPage):
                results.append(item)
            elif isinstance(item, Exception):
                logger.warning(f"[ETL/extract] Task error: {item}")

    logger.info(f"[ETL/extract] Fetched {len(results)}/{len(urls)} pages")
    return results


async def extract_from_source(source: SourceConfig) -> list[FetchedPage]:
    """Run full extraction for a source config."""
    all_urls: list[str] = list(source.glossary_urls)

    # Discover from sitemap if available
    if source.sitemap_url:
        sitemap_urls = await discover_urls_from_sitemap(
            source.sitemap_url, source.url_pattern
        )
        all_urls.extend(sitemap_urls)

    # Deduplicate
    all_urls = list(dict.fromkeys(all_urls))

    # Limit
    if len(all_urls) > source.max_pages:
        logger.info(f"[ETL/extract] Limiting {source.name} from {len(all_urls)} to {source.max_pages} URLs")
        all_urls = all_urls[:source.max_pages]

    logger.info(f"[ETL/extract] Extracting {len(all_urls)} pages from {source.name}...")
    return await fetch_pages(all_urls, delay_seconds=source.delay_seconds)
