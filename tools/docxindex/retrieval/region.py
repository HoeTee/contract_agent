from __future__ import annotations

from typing import Any

from tools.docxindex.llm.schemas import RouteStep

from .title import _candidate


def region_matches(index: dict[str, Any], step: RouteStep, prior: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = index.get("nodes") or []
    by_id = {node.get("node_id"): node for node in nodes}
    result = []
    region_ids = {
        (index.get("top_regions") or {}).get(region, region)
        for region in step.regions
    }
    if not step.terms:
        for node_id in region_ids:
            if node_id in by_id:
                node = by_id[node_id]
                children = node.get("nodes") or node.get("children") or []
                if node.get("node_type") in {"body", "attachments"} and children:
                    for child_id in children:
                        child = by_id.get(child_id if isinstance(child_id, str) else child_id.get("node_id"))
                        if child:
                            result.append(_candidate(child, "region"))
                else:
                    result.append(_candidate(node, "region"))
    if step.terms:
        for match in prior:
            node = by_id.get(match.get("node_id"))
            if node and _in_regions(str(node.get("node_id") or ""), region_ids) and any(
                term in str(node.get("title") or "") for term in step.terms
            ):
                result.append(_candidate(node, "region"))
    for node in nodes:
        title = str(node.get("title") or "")
        node_id = str(node.get("node_id") or "")
        if step.terms and _in_regions(node_id, region_ids) and any(term in title for term in step.terms):
            result.append(_candidate(node, "region"))
    return _unique(result)


def _in_regions(node_id: str, region_ids: set[str]) -> bool:
    if not region_ids:
        return True
    return any(node_id == region_id or node_id.startswith(f"{region_id}/") for region_id in region_ids)


def _unique(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for match in matches:
        node_id = match.get("node_id")
        if node_id and node_id not in seen:
            seen.add(node_id)
            result.append(match)
    return result
