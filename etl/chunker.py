"""
etl/chunker.py
Chunking phase — split documents into embeddable chunks using RecursiveCharacterTextSplitter.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    """A single text chunk with metadata."""
    chunk_id: str
    text: str
    title: str
    source: str
    category: str
    tags: list[str] = field(default_factory=list)
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.chunk_id:
            content_hash = hashlib.md5(self.text.encode()).hexdigest()[:12]
            self.chunk_id = f"{self.category}_{content_hash}"


def chunk_document(
    title: str,
    content: str,
    source: str,
    category: str,
    tags: Optional[list[str]] = None,
    updated_at: str = "",
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Split a document into chunks using RecursiveCharacterTextSplitter.
    Falls back to simple splitting if langchain not available.
    """
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n## ",      # Heading level 2
                "\n### ",     # Heading level 3
                "\n#### ",    # Heading level 4
                "\n\n",       # Paragraph break
                "\n",         # Line break
                ". ",         # Sentence boundary
                ", ",         # Clause boundary
                " ",          # Word boundary
            ],
            length_function=len,
        )
        texts = splitter.split_text(content)
    except ImportError:
        logger.warning("[ETL/chunker] langchain_text_splitters not available, using simple split")
        texts = _simple_split(content, chunk_size, chunk_overlap)

    chunks = []
    for i, text in enumerate(texts):
        text = text.strip()
        if len(text) < 50:  # Skip very small chunks
            continue

        chunk = Chunk(
            chunk_id="",
            text=text,
            title=title,
            source=source,
            category=category,
            tags=tags or [],
            chunk_index=i,
            total_chunks=len(texts),
            metadata={
                "topic": _infer_topic(text, category),
                "category": category,
                "difficulty": _infer_difficulty(text),
                "source": source,
                "title": title,
                "updated_at": updated_at,
            },
        )
        chunks.append(chunk)

    return chunks


def _simple_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Fallback: simple character-based splitting."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


def _infer_topic(text: str, category: str) -> str:
    """Infer topic from content keywords."""
    text_lower = text.lower()
    topic_keywords = {
        "risk_management": ["risk", "var", "volatility", "hedging", "rủi ro"],
        "portfolio_theory": ["portfolio", "diversif", "sharpe", "efficient frontier", "danh mục"],
        "derivatives": ["option", "future", "swap", "derivative", "phái sinh"],
        "valuation": ["valuation", "dcf", "capm", "p/e", "định giá"],
        "accounting": ["balance sheet", "income statement", "cash flow", "bctc", "kế toán"],
        "economics": ["gdp", "inflation", "interest rate", "monetary", "lạm phát", "lãi suất"],
        "banking": ["bank", "loan", "deposit", "nim", "npl", "ngân hàng"],
        "investing": ["invest", "stock", "bond", "fund", "đầu tư", "cổ phiếu"],
    }
    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return category


def _infer_difficulty(text: str) -> str:
    """Infer difficulty level from content complexity."""
    text_lower = text.lower()
    advanced_terms = [
        "stochastic", "monte carlo", "black-scholes", "copula",
        "eigenvalue", "convexity", "martingale", "itô",
    ]
    intermediate_terms = [
        "standard deviation", "correlation", "regression",
        "capm", "wacc", "dcf", "beta", "alpha",
    ]
    if any(t in text_lower for t in advanced_terms):
        return "advanced"
    if any(t in text_lower for t in intermediate_terms):
        return "intermediate"
    return "beginner"


def chunk_documents(documents: list, **kwargs) -> list[Chunk]:
    """Chunk multiple CleanedDocuments."""
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(
            title=doc.title,
            content=doc.content,
            source=doc.source,
            category=doc.category,
            tags=doc.tags,
            updated_at=getattr(doc, "updated_at", ""),
            **kwargs,
        )
        all_chunks.extend(chunks)

    logger.info(f"[ETL/chunker] Created {len(all_chunks)} chunks from {len(documents)} documents")
    return all_chunks
