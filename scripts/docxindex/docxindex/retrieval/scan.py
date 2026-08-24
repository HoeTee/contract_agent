from __future__ import annotations

from typing import Any

from docxindex.indexing import estimate_tokens

from .title import _candidate


def scan_matches(index: dict[str, Any], batch_tokens: int = 12000) -> list[dict[str, Any]]:
    by_id = {node.get("node_id"): node for node in index.get("nodes") or []}
    records = []
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
        records.append((anchor_id, record, owner, text))

    result = []
    batch = []
    used = 0
    for item in records:
        tokens = estimate_tokens(item[3])
        if batch and used + tokens > batch_tokens:
            result.append(_scan_batch(batch, len(result) + 1))
            batch = []
            used = 0
        batch.append(item)
        used += tokens
    if batch:
        result.append(_scan_batch(batch, len(result) + 1))
    return result


def _scan_batch(batch: list[tuple[str, dict[str, Any], dict[str, Any], str]], batch_index: int) -> dict[str, Any]:
    first_anchor, first_record, first_owner, _ = batch[0]
    last_anchor, last_record, _, _ = batch[-1]
    candidate = _candidate(first_owner, "scan")
    candidate.update(
        {
            "node_id": f"scan/batch_{batch_index:03d}",
            "parent_node_id": first_owner.get("node_id"),
            "text_override": "\n".join(item[3] for item in batch),
            "start_index": first_record.get("body_child_index"),
            "end_index": last_record.get("body_child_index"),
            "start_anchor": first_anchor,
            "end_anchor": last_anchor,
        }
    )
    return candidate
