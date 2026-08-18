"""
retrieval/reranker.py
Cross-encoder reranker for improving retrieval precision.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_RERANKER = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


@dataclass
class RerankResult:
    doc_index: int
    score: float


class Reranker:
    """Cross-encoder reranker using sentence-transformers CrossEncoder."""

    def __init__(self, model_name: str = DEFAULT_RERANKER):
        self._model_name = model_name
        self._model = None
        self._loaded = False

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            logger.info(f"[Reranker] Loading {self._model_name}...")
            self._model = CrossEncoder(self._model_name, max_length=512)
            self._loaded = True
            logger.info(f"[Reranker] Model loaded")
        except ImportError:
            logger.warning("[Reranker] sentence-transformers not installed")
        except Exception as e:
            logger.warning(f"[Reranker] Failed to load: {e}")

    @property
    def is_available(self) -> bool:
        return self._loaded

    def rerank(
        self,
        query: str,
        documents: list[str],
        doc_indices: list[int],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """
        Rerank candidate documents using cross-encoder.

        Args:
            query: The search query
            documents: List of document texts (candidates)
            doc_indices: Original indices of these documents
            top_k: Number of top results to return
        """
        self._load_model()
        if self._model is None or not documents:
            return [
                RerankResult(doc_index=idx, score=0.0)
                for idx in doc_indices[:top_k]
            ]

        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs)

        results = [
            RerankResult(doc_index=doc_indices[i], score=float(scores[i]))
            for i in range(len(scores))
        ]
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
