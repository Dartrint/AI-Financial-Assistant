"""
etl/loader.py
Load phase — embed chunks and upsert into Qdrant vector store.
"""

from __future__ import annotations

import logging
import os
import uuid

from config import BGE_MODEL

logger = logging.getLogger(__name__)


def load_chunks_to_qdrant(
    chunks: list,  # list[Chunk]
    collection_name: str,
    qdrant_path: str | None = None,
    batch_size: int = 64,
) -> int:
    """
    Embed chunks and upsert into Qdrant collection.

    Returns number of chunks loaded.
    """
    if not chunks:
        return 0

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    # Connect to Qdrant (local persistence)
    if qdrant_path is None:
        qdrant_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "qdrant_data"
        )
    os.makedirs(qdrant_path, exist_ok=True)
    client = QdrantClient(path=qdrant_path)

    # Load embedding model
    from sentence_transformers import SentenceTransformer
    logger.info(f"[ETL/loader] Loading embedding model {BGE_MODEL}...")
    model = SentenceTransformer(BGE_MODEL)
    vector_size = model.get_sentence_embedding_dimension()

    # Ensure collection exists
    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info(f"[ETL/loader] Created collection '{collection_name}' (dim={vector_size})")

    # Embed and upsert in batches
    total_loaded = 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.text for c in batch]

        # Embed
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        # Build points
        points = []
        for j, chunk in enumerate(batch):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{chunk.source}:{chunk.chunk_index}"))
            payload = {
                "text": chunk.text,
                "title": chunk.title,
                "source": chunk.source,
                "category": chunk.category,
                "tags": chunk.tags,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                **chunk.metadata,
            }
            points.append(PointStruct(
                id=point_id,
                vector=embeddings[j].tolist(),
                payload=payload,
            ))

        client.upsert(collection_name=collection_name, points=points)
        total_loaded += len(points)
        logger.info(f"[ETL/loader] Loaded batch {i // batch_size + 1}: {len(points)} points → {collection_name}")

    logger.info(f"[ETL/loader] Total loaded: {total_loaded} chunks into '{collection_name}'")
    return total_loaded


def load_seed_json_to_qdrant(
    json_path: str,
    collection_name: str,
    category: str,
    qdrant_path: str | None = None,
) -> int:
    """Load a seed JSON knowledge file into Qdrant."""
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data if isinstance(data, list) else data.get("entries", [])

    from etl.chunker import Chunk

    chunks = []
    for i, entry in enumerate(entries):
        title = entry.get("term", entry.get("title", entry.get("concept", f"entry_{i}")))
        parts = [title]
        for key in ["definition", "content", "description"]:
            if entry.get(key):
                parts.append(entry[key])
        for key in ["formula", "formula_latex", "formula_python", "example", "context_vn", "interpretation"]:
            if entry.get(key):
                parts.append(f"{key}: {entry[key]}")

        text = "\n".join(parts)
        chunk = Chunk(
            chunk_id="",
            text=text,
            title=title,
            source=f"seed:{os.path.basename(json_path)}",
            category=category,
            tags=entry.get("tags", [entry.get("category", category)]),
            chunk_index=i,
            total_chunks=len(entries),
            metadata={
                "topic": entry.get("category", category),
                "category": category,
                "difficulty": "beginner",
                "source": f"seed:{os.path.basename(json_path)}",
                "title": title,
            },
        )
        chunks.append(chunk)

    return load_chunks_to_qdrant(chunks, collection_name, qdrant_path)
