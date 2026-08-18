"""
retrieval/embedding_retriever.py
Dense embedding retrieval using BGE model via sentence-transformers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from config import BGE_MODEL

logger = logging.getLogger(__name__)

DEFAULT_MODEL = BGE_MODEL


@dataclass
class EmbeddingResult:
    doc_index: int
    score: float


class EmbeddingRetriever:
    """Dense embedding retriever using sentence-transformers BGE model."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._indexed = False

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            logger.info(f"[Embedding] Loading model {self._model_name}...")
            self._model = SentenceTransformer(self._model_name)
            logger.info(f"[Embedding] Model loaded: {self._model_name}")
        except ImportError:
            logger.warning("[Embedding] sentence-transformers not installed")
        except Exception as e:
            logger.warning(f"[Embedding] Failed to load model: {e}")

    def build_index(self, documents: list[str]) -> None:
        """Encode documents and build embedding index."""
        self._load_model()
        if self._model is None:
            return

        logger.info(f"[Embedding] Encoding {len(documents)} documents...")
        self._embeddings = self._model.encode(
            documents,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        self._indexed = True
        logger.info(f"[Embedding] Index built: {self._embeddings.shape}")

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def search(self, query: str, top_k: int = 10) -> list[EmbeddingResult]:
        """Search using cosine similarity."""
        if not self._indexed or self._model is None or self._embeddings is None:
            return []

        query_emb = self._model.encode(
            [query], normalize_embeddings=True
        )
        scores = np.dot(self._embeddings, query_emb.T).flatten()

        top_indices = np.argsort(scores)[::-1][:top_k]
        return [
            EmbeddingResult(doc_index=int(idx), score=float(scores[idx]))
            for idx in top_indices
            if scores[idx] > 0.0
        ]
