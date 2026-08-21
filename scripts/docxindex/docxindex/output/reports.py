from __future__ import annotations

from pathlib import Path
from typing import Any

from docxindex.indexing import document_mode, estimate_tokens


def structure_tokens(index: dict[str, Any]) -> int:
    import json

    return estimate_tokens(json.dumps(index["structure_tree"], ensure_ascii=False))


def title_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    title_types = {
        "section",
        "attachment_parent",
        "attachment_section",
        "visual_title",
        "heading",
        "plain_label",
    }
    return [
        {
            "node_id": node["node_id"],
            "level": node.get("level"),
            "node_type": node.get("node_type"),
            "title": node.get("title"),
            "token_estimate": node.get("token_estimate"),
            "start_anchor": node.get("start_anchor"),
            "end_anchor": node.get("end_anchor"),
        }
        for node in index["nodes"]
        if node.get("node_type") in title_types
    ]


def token_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node["node_id"],
            "node_type": node.get("node_type"),
            "level": node.get("level"),
            "token_estimate": node.get("token_estimate") or 0,
            "title": node.get("title") or "",
            "start_anchor": node.get("start_anchor") or "",
            "end_anchor": node.get("end_anchor") or "",
        }
        for node in sorted(index["nodes"], key=lambda item: item.get("token_estimate") or 0, reverse=True)
    ]


def attachment_tree(index: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = {node["node_id"]: node for node in index["nodes"]}

    def build(node_id: str) -> dict[str, Any]:
        node = nodes[node_id]
        return {
            "node_id": node["node_id"],
            "node_type": node.get("node_type"),
            "title": node.get("title"),
            "token_estimate": node.get("token_estimate"),
            "children": [build(child_id) for child_id in node.get("children") or []],
        }

    attachments = nodes.get("attachments")
    if not attachments:
        return []
    return [build(child_id) for child_id in attachments.get("children") or []]


def write_report(path: Path, docx: Path, index: dict[str, Any], out_dir: Path) -> None:
    tokens = structure_tokens(index)
    top_types: dict[str, int] = {}
    for node in index["nodes"]:
        node_type = node.get("node_type") or "unknown"
        top_types[node_type] = top_types.get(node_type, 0) + 1

    largest = token_rows(index)[:10]
    lines = [
        f"source_file: {docx}",
        f"output_dir: {out_dir}",
        f"schema_version: {index.get('schema_version')}",
        f"nodes: {len(index['nodes'])}",
        f"anchors: {len(index['anchor_map'])}",
        f"structure_tokens: {tokens}",
        f"document_structure_mode: {document_mode(tokens)}",
        "",
        "node_type_counts:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in sorted(top_types.items()))
    lines.extend(["", "largest_nodes:"])
    lines.extend(f"  {row['token_estimate']:>5}  {row['node_id']}  {row['title'][:80]}" for row in largest)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
