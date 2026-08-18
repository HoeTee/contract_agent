from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_node(index: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in index["nodes"]:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"node_id not found: {node_id}")
