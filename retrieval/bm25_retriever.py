"""
retrieval/bm25_retriever.py
BM25 sparse retrieval over knowledge documents.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BM25Result:
    doc_index: int
    score: float


def _tokenize_vi(text: str) -> list[str]:
    """Simple word-level tokenizer for Vietnamese text."""
    text = text.lower()
    text = re.sub(r"[^\w\sàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", " ", text)
    return [w for w in text.split() if len(w) >= 2]


class BM25Retriever:
    """BM25 sparse keyword retriever using rank-bm25."""

    def __init__(self):
        self._bm25 = None
        self._corpus_tokens: list[list[str]] = []
        self._indexed = False

    def build_index(self, documents: list[str]) -> None:
        """Build BM25 index from document texts."""
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
        except ImportError:
            logger.warning("[BM25] rank-bm25 not installed")
            return

        self._corpus_tokens = [_tokenize_vi(doc) for doc in documents]
        self._bm25 = BM25Okapi(self._corpus_tokens)
        self._indexed = True
        logger.info(f"[BM25] Indexed {len(documents)} documents")

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def search(self, query: str, top_k: int = 10) -> list[BM25Result]:
        """Search for documents matching the query."""
        if not self._indexed or self._bm25 is None:
            return []

        query_tokens = _tokenize_vi(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        return [
            BM25Result(doc_index=idx, score=score)
            for idx, score in indexed_scores[:top_k]
        ]
