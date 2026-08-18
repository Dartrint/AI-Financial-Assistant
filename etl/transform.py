"""
etl/transform.py
Transform phase — clean HTML to structured content using Trafilatura + BS4.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CleanedDocument:
    """Cleaned and structured document from a web page."""
    title: str
    content: str
    source: str  # URL
    category: str
    tags: list[str] = field(default_factory=list)
    updated_at: str = ""
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.md5(self.content.encode()).hexdigest()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


def extract_with_trafilatura(html: str, url: str) -> Optional[dict]:
    """Extract main content using Trafilatura."""
    try:
        import trafilatura
        result = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_links=False,
            output_format="txt",
            favor_recall=True,
        )
        if result and len(result.strip()) > 100:
            # Extract title
            metadata = trafilatura.extract(
                html, url=url, output_format="xml",
                include_comments=False,
            )
            title = ""
            if metadata:
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(metadata)
                    title = root.attrib.get("title", "")
                except Exception:
                    pass
            return {"content": result.strip(), "title": title}
    except Exception as e:
        logger.debug(f"[ETL/transform] Trafilatura failed for {url}: {e}")
    return None


def extract_with_bs4(html: str, url: str) -> Optional[dict]:
    """Fallback: extract content using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # Remove unwanted elements
        for tag in soup.find_all(["nav", "header", "footer", "aside", "script",
                                   "style", "noscript", "iframe", "form"]):
            tag.decompose()

        # Remove ad-related elements
        for tag in soup.find_all(attrs={"class": re.compile(
            r"ad|advertisement|sidebar|related|social|share|comment|newsletter|popup",
            re.IGNORECASE
        )}):
            tag.decompose()

        # Get title
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

        # Get main content
        main = soup.find("main") or soup.find("article") or soup.find(
            attrs={"role": "main"}
        )
        if main is None:
            main = soup.find("body")

        if main:
            text = main.get_text(separator="\n", strip=True)
            # Clean excessive whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" {2,}", " ", text)
            if len(text.strip()) > 100:
                return {"content": text.strip(), "title": title}
    except Exception as e:
        logger.debug(f"[ETL/transform] BS4 failed for {url}: {e}")
    return None


def transform_page(
    html: str,
    url: str,
    category: str = "",
    tags: Optional[list[str]] = None,
) -> Optional[CleanedDocument]:
    """
    Transform raw HTML into a clean, structured document.
    Tries Trafilatura first, falls back to BeautifulSoup.
    """
    # Try Trafilatura
    result = extract_with_trafilatura(html, url)

    # Fallback to BS4
    if result is None:
        result = extract_with_bs4(html, url)

    if result is None:
        logger.warning(f"[ETL/transform] Could not extract content from {url}")
        return None

    content = result["content"]
    title = result.get("title", "")

    # Infer title from URL if missing
    if not title:
        path = url.rstrip("/").split("/")[-1]
        title = path.replace("-", " ").replace("_", " ").title()

    # Skip very short content
    if len(content) < 150:
        logger.debug(f"[ETL/transform] Content too short ({len(content)} chars): {url}")
        return None

    return CleanedDocument(
        title=title,
        content=content,
        source=url,
        category=category,
        tags=tags or [],
    )


def transform_pages(
    pages: list,  # list[FetchedPage]
    category: str = "",
    tags: Optional[list[str]] = None,
) -> list[CleanedDocument]:
    """Transform multiple fetched pages."""
    docs = []
    for page in pages:
        doc = transform_page(page.html, page.url, category, tags)
        if doc:
            docs.append(doc)
    logger.info(f"[ETL/transform] Transformed {len(docs)}/{len(pages)} pages")
    return docs
