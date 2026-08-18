from __future__ import annotations

from typing import Any


def get_node(index: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in index["nodes"]:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"node_id not found: {node_id}")


def content_view(index: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = get_node(index, node_id)
    return {
        key: node.get(key)
        for key in ("node_id", "title", "node_type", "text", "start_anchor", "end_anchor", "token_estimate")
    }
