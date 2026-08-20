from __future__ import annotations

from typing import Any

from .title import _candidate


def scan_matches(index: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {node.get("node_id"): node for node in index.get("nodes") or []}
    result = []
    anchors = sorted(
        (index.get("anchor_map") or {}).items(),
        key=lambda item: item[1].get("body_child_index") or 0,
    )
    for anchor_id, record in anchors:
        owner_id = record.get("node_id")
        owner = by_id.get(owner_id)
        text = str(record.get("text") or "").strip()
        if not owner or not text:
            continue
        candidate = _candidate(owner, "scan")
        candidate.update(
            {
                "node_id": f"{owner_id}/scan_{anchor_id}",
                "parent_node_id": owner_id,
                "text_override": text,
                "start_index": record.get("body_child_index"),
                "end_index": record.get("body_child_index"),
                "start_anchor": anchor_id,
                "end_anchor": anchor_id,
            }
        )
        result.append(candidate)
    return result
