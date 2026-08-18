"""
knowledge/loader.py
Knowledge base loader — loads seed JSON files into Qdrant on startup.
Maintains backward-compatible KnowledgeBase interface.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from knowledge.qdrant_store import QdrantKnowledgeStore

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = os.path.dirname(__file__)


@dataclass
class KnowledgeDocument:
    """A single knowledge document (for backward compatibility)."""
    id: str
    title: str
    content: str
    category: str
    source_file: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        parts = [self.title, self.content]
        for key in ["term_en", "formula", "example", "formula_python", "context_vn"]:
            if self.metadata.get(key):
                parts.append(str(self.metadata[key]))
        return " ".join(parts)


# Mapping seed files → Qdrant collections
SEED_MAP = {
    "financial_terms.json": ("financial_glossary", "financial_glossary"),
    "economics_theory.json": ("economics_glossary", "economics"),
    "quant_finance.json": ("quant_finance", "quant_finance"),
    "vietnam_market.json": ("vietnam_market", "vietnam_market"),
}


class KnowledgeBase:
    """
    Knowledge base backed by Qdrant vector store.

    On load():
    1. Ensures Qdrant collections exist
    2. Loads seed JSON files if collections are empty
    3. Provides search interface via Qdrant
    """

    def __init__(self):
        self._qdrant_store = QdrantKnowledgeStore()
        self._documents: list[KnowledgeDocument] = []
        self._loaded = False

    def load(self) -> None:
        """Load seed data into Qdrant if not already populated."""
        if self._loaded:
            return

        # Qdrant improves persistence but is not a prerequisite for local RAG.
        # The in-memory corpus below leaves BM25 usable in a minimal dev setup.
        try:
            from knowledge.collections import ensure_collections
            ensure_collections()
            if not self._qdrant_store.is_populated():
                logger.info("[KnowledgeBase] Collections empty — loading seed data...")
                self._load_seed_data()
            else:
                logger.info("[KnowledgeBase] Collections already populated")
        except Exception as exc:
            logger.warning("[KnowledgeBase] Qdrant unavailable; using in-memory RAG: %s", exc)

        # Also load documents into memory for backward compat
        self._load_documents_from_json()
        self._loaded = True
        logger.info(f"[KnowledgeBase] Ready: {len(self._documents)} docs, Qdrant populated")

    def _load_seed_data(self) -> None:
        """Load seed JSON files into Qdrant using ETL loader."""
        try:
            from etl.loader import load_seed_json_to_qdrant
            for filename, (collection, category) in SEED_MAP.items():
                filepath = os.path.join(KNOWLEDGE_DIR, filename)
                if os.path.exists(filepath):
                    count = load_seed_json_to_qdrant(filepath, collection, category)
                    logger.info(f"[KnowledgeBase] Seeded {count} entries → {collection}")
        except Exception as e:
            logger.warning(f"[KnowledgeBase] Seed loading error: {e}")

    def _load_documents_from_json(self) -> None:
        """Load JSON files into memory for backward compatibility."""
        json_files = [f for f in os.listdir(KNOWLEDGE_DIR) if f.endswith(".json")]
        for filename in json_files:
            filepath = os.path.join(KNOWLEDGE_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries = data if isinstance(data, list) else data.get("entries", [])
                category = filename.replace(".json", "")
                for i, entry in enumerate(entries):
                    doc = KnowledgeDocument(
                        id=f"{category}_{i}",
                        title=entry.get("term", entry.get("title", entry.get("concept", f"entry_{i}"))),
                        content=entry.get("definition", entry.get("content", entry.get("description", ""))),
                        category=category,
                        source_file=filename,
                        metadata={k: v for k, v in entry.items()
                                  if k not in ("term", "title", "concept", "definition", "content", "description")},
                    )
                    self._documents.append(doc)
            except Exception as e:
                logger.warning(f"[KnowledgeBase] Error loading {filename}: {e}")

    def search(self, query: str, top_k: int = 5, collections: list[str] | None = None) -> list:
        """Search using Qdrant vector store."""
        return self._qdrant_store.search(query, collections=collections, top_k=top_k)

    def get_all_documents(self) -> list[KnowledgeDocument]:
        return list(self._documents)

    def get_all_texts(self) -> list[str]:
        return [doc.full_text for doc in self._documents]

    def stats(self) -> dict:
        qdrant_stats = self._qdrant_store.stats()
        return {
            "total_documents": len(self._documents),
            "loaded": self._loaded,
            "qdrant_collections": qdrant_stats,
        }
