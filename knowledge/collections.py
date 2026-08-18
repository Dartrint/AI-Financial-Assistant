"""
knowledge/collections.py
Qdrant collection definitions and management.

Uses a process-wide singleton QdrantClient to avoid concurrent-access
lock errors when the local file-based backend is in use.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qdrant_data")
BGE_MODEL = os.getenv("BGE_MODEL", "BAAI/bge-small-en-v1.5")

# Vector dimension by model
MODEL_DIMENSIONS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "intfloat/multilingual-e5-small": 384,
    "intfloat/multilingual-e5-base": 768,
}


@dataclass
class CollectionDef:
    name: str
    description: str
    vector_size: int = 384


COLLECTIONS: dict[str, CollectionDef] = {
    "financial_glossary": CollectionDef(
        name="financial_glossary",
        description="Financial terms and definitions from Investopedia, SEC, CFI",
        vector_size=MODEL_DIMENSIONS.get(BGE_MODEL, 384),
    ),
    "economics_glossary": CollectionDef(
        name="economics_glossary",
        description="Economics theory from IMF, World Bank, Khan Academy",
        vector_size=MODEL_DIMENSIONS.get(BGE_MODEL, 384),
    ),
    "quant_finance": CollectionDef(
        name="quant_finance",
        description="Quantitative finance from QuantConnect, CFA materials",
        vector_size=MODEL_DIMENSIONS.get(BGE_MODEL, 384),
    ),
    "vietnam_market": CollectionDef(
        name="vietnam_market",
        description="Vietnam market knowledge from Vietstock, SSI, Vietcap",
        vector_size=MODEL_DIMENSIONS.get(BGE_MODEL, 384),
    ),
    "research_reports": CollectionDef(
        name="research_reports",
        description="Research reports and market analysis",
        vector_size=MODEL_DIMENSIONS.get(BGE_MODEL, 384),
    ),
}


# ---------------------------------------------------------------------------
# Singleton Qdrant client — one per qdrant_path
# ---------------------------------------------------------------------------
_client_lock = threading.Lock()
_shared_clients: dict[str, object] = {}


def get_shared_client(qdrant_path: str = QDRANT_PATH):
    """Return (or create) the process-wide singleton QdrantClient for *qdrant_path*.

    Using a single client prevents the "Storage folder is already accessed by
    another instance of Qdrant client" error that occurs when multiple
    QdrantClient instances open the same local path concurrently.
    """
    with _client_lock:
        if qdrant_path not in _shared_clients:
            from qdrant_client import QdrantClient
            os.makedirs(qdrant_path, exist_ok=True)
            _shared_clients[qdrant_path] = QdrantClient(path=qdrant_path)
            logger.info("[Qdrant] Singleton client created for %s", qdrant_path)
        return _shared_clients[qdrant_path]


def ensure_collections(qdrant_path: str = QDRANT_PATH) -> dict[str, bool]:
    """Create all collections in Qdrant if they don't exist."""
    from qdrant_client.models import Distance, VectorParams

    client = get_shared_client(qdrant_path)

    existing = [c.name for c in client.get_collections().collections]
    results = {}

    for name, cdef in COLLECTIONS.items():
        if name in existing:
            results[name] = True
            continue
        try:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=cdef.vector_size,
                    distance=Distance.COSINE,
                ),
            )
            results[name] = True
            logger.info(f"[Qdrant] Created collection '{name}' (dim={cdef.vector_size})")
        except Exception as e:
            logger.error(f"[Qdrant] Failed to create '{name}': {e}")
            results[name] = False

    return results


def get_collection_stats(qdrant_path: str = QDRANT_PATH) -> dict[str, dict]:
    """Get stats for all collections."""
    try:
        client = get_shared_client(qdrant_path)
        stats = {}
        for name in COLLECTIONS:
            try:
                info = client.get_collection(name)
                stats[name] = {
                    "points_count": info.points_count,
                    "vectors_count": info.vectors_count,
                    "status": info.status.value if info.status else "unknown",
                }
            except Exception:
                stats[name] = {"points_count": 0, "status": "not_found"}
        return stats
    except Exception as e:
        logger.warning(f"[Qdrant] Stats error: {e}")
        return {}
