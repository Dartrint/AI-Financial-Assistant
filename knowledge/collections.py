"""
knowledge/collections.py
Qdrant collection definitions and management.
"""

from __future__ import annotations

import logging
import os
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


def ensure_collections(qdrant_path: str = QDRANT_PATH) -> dict[str, bool]:
    """Create all collections in Qdrant if they don't exist."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    os.makedirs(qdrant_path, exist_ok=True)
    client = QdrantClient(path=qdrant_path)

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
        from qdrant_client import QdrantClient
        client = QdrantClient(path=qdrant_path)
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
