from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from .client import EmbeddingClient
from .schema import VectorIndex, VectorItem, VectorMetadata


def build_vector_index(
    index: dict[str, Any],
    client: EmbeddingClient,
    source_index: str = "document_index.json",
    concurrency: int = 10,
) -> VectorIndex:
    entries = _select_vector_entries(index)
    limiter = BoundedSemaphore(max(1, concurrency))
    with limiter:
        embeddings = client.embed([entry["vector_text"] for entry in entries])
    items = []
    for entry, embedding in zip(entries, embeddings):
        node = entry["node"]
        items.append(
            VectorItem(
                vector_id=node["node_id"],
                node_id=node["node_id"],
                text_hash=_text_hash(entry["vector_text"]),
                text=entry["vector_text"],
                embedding=embedding,
                metadata=VectorMetadata(
                    title=node.get("title") or "",
                    node_type=node.get("node_type") or "",
                    start_anchor=node.get("start_anchor"),
                    end_anchor=node.get("end_anchor"),
                    token_estimate=int(node.get("token_estimate") or 0),
                ),
            )
        )
    return VectorIndex(source_index=source_index, embedding_model=client.settings.model, items=items)


def save_vector_index(path: Path, index: VectorIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")


def load_vector_index(path: Path) -> VectorIndex:
    return VectorIndex.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _select_vector_entries(index: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for node in index.get("nodes") or []:
        if not _should_index_node(node):
            continue
        vector_text = _vector_text(node)
        if vector_text:
            result.append({"node": node, "vector_text": vector_text})
    return result


def _should_index_node(node: dict[str, Any]) -> bool:
    node_type = node.get("node_type")
    text = (node.get("text") or "").strip()
    children = node.get("children") or []
    if node_type in {"body", "attachments"}:
        return False
    if node_type == "table":
        return bool(text)
    if children and not text:
        return False
    return bool(text)


def _vector_text(node: dict[str, Any]) -> str:
    parts = [
        f"标题：{node.get('title') or ''}",
        f"摘要：{node.get('summary') or ''}",
        f"正文：{node.get('text') or ''}",
    ]
    return "\n".join(part for part in parts if part.strip()).strip()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
