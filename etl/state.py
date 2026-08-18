"""Local manifest that makes web knowledge ingestion incremental and auditable."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


DEFAULT_STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "etl_state.json")


def load_state(path: str = DEFAULT_STATE_PATH) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
            return state if isinstance(state, dict) else {"version": 1, "sources": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 1, "sources": {}}


def changed_documents(documents: list, state: dict[str, Any], source_name: str) -> list:
    known = state.get("sources", {}).get(source_name, {}).get("documents", {})
    return [doc for doc in documents if known.get(doc.source, {}).get("content_hash") != doc.content_hash]


def record_documents(documents: list, state: dict[str, Any], source_name: str, path: str = DEFAULT_STATE_PATH) -> None:
    source_state = state.setdefault("sources", {}).setdefault(source_name, {"documents": {}})
    source_state["documents"] = {
        doc.source: {"content_hash": doc.content_hash, "title": doc.title} for doc in documents
    }
    source_state["last_successful_ingestion_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
