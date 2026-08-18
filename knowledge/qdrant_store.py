"""
knowledge/qdrant_store.py
Qdrant vector store wrapper for knowledge retrieval.
Supports multi-collection search.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from config import BGE_MODEL

logger = logging.getLogger(__name__)

QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qdrant_data")


@dataclass
class SearchResult:
    """A single search result from Qdrant."""
    text: str
    title: str
    source: str
    category: str
    score: float
    collection: str
    metadata: dict[str, Any] = field(default_factory=dict)


class QdrantKnowledgeStore:
    """Qdrant-backed knowledge store with multi-collection search."""

    def __init__(self, qdrant_path: str = QDRANT_PATH, model_name: str = BGE_MODEL):
        self._qdrant_path = qdrant_path
        self._model_name = model_name
        self._client = None
        self._embed_model = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            os.makedirs(self._qdrant_path, exist_ok=True)
            self._client = QdrantClient(path=self._qdrant_path)
        return self._client

    def _get_embed_model(self):
        if self._embed_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[QdrantStore] Loading embedding model {self._model_name}...")
            self._embed_model = SentenceTransformer(self._model_name)
        return self._embed_model

    def search(
        self,
        query: str,
        collections: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        Search across one or more Qdrant collections.
        If collections is None, searches all available collections.
        """
        client = self._get_client()
        model = self._get_embed_model()

        # Embed query
        query_vector = model.encode(query, normalize_embeddings=True).tolist()

        # Determine which collections to search
        if collections is None:
            from knowledge.collections import COLLECTIONS
            collections = list(COLLECTIONS.keys())

        all_results: list[SearchResult] = []

        for collection_name in collections:
            try:
                hits = client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    with_payload=True,
                )
                for hit in hits:
                    payload = hit.payload or {}
                    all_results.append(SearchResult(
                        text=payload.get("text", ""),
                        title=payload.get("title", ""),
                        source=payload.get("source", ""),
                        category=payload.get("category", collection_name),
                        score=float(hit.score),
                        collection=collection_name,
                        metadata={
                            k: v for k, v in payload.items()
                            if k not in ("text", "title", "source", "category")
                        },
                    ))
            except Exception as e:
                logger.debug(f"[QdrantStore] Search error in {collection_name}: {e}")

        # Sort by score descending, take top_k
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]

    def search_collection(
        self, query: str, collection: str, top_k: int = 5
    ) -> list[SearchResult]:
        """Search a single collection."""
        return self.search(query, collections=[collection], top_k=top_k)

    def is_populated(self) -> bool:
        """Check if any collection has data."""
        try:
            client = self._get_client()
            from knowledge.collections import COLLECTIONS
            for name in COLLECTIONS:
                try:
                    info = client.get_collection(name)
                    if info.points_count and info.points_count > 0:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def stats(self) -> dict:
        from knowledge.collections import get_collection_stats
        return get_collection_stats(self._qdrant_path)
