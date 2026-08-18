from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from docx_retrieval import build_document_index, estimate_tokens, get_node, write_json
from docx_retrieval.retriever import keyword_search


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def safe_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r'[<>:"/\\|?*\s]+', "_", name).strip("._")
    return name[:120] or "document"


def iter_docx_inputs(path: Path, batch: bool) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".docx":
            raise ValueError(f"input file must be .docx: {path}")
        return [path]
    if path.is_dir():
        if not batch:
            raise ValueError("directory input requires --batch")
        return [p for p in sorted(path.rglob("*.docx")) if not p.name.startswith("~$")]
    raise FileNotFoundError(path)


def structure_tokens(index: dict[str, Any]) -> int:
    return estimate_tokens(json.dumps(index["structure_tree"], ensure_ascii=False))


def document_mode(tokens: int) -> str:
    if tokens <= 6000:
        return "compact_structure"
    if tokens <= 20000:
        return "paged_structure"
    return "filtered_or_paged_structure"


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


def search_index(index: dict[str, Any], keywords: list[str]) -> list[dict[str, Any]]:
    return keyword_search(index, keywords)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["node_id"]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    lines.extend(
        f"  {row['token_estimate']:>5}  {row['node_id']}  {row['title'][:80]}"
        for row in largest
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_document_outputs(docx: Path, root_out: Path, query: list[str], node_id: str | None) -> dict[str, Any]:
    index = build_document_index(docx)
    doc_out = root_out / safe_name(docx)
    doc_out.mkdir(parents=True, exist_ok=True)

    write_json(doc_out / "document_index.json", index)
    write_json(doc_out / "structure_tree.json", index["structure_tree"])
    write_json(doc_out / "titles.json", {"titles": title_rows(index)})
    write_csv(doc_out / "node_tokens.csv", token_rows(index))
    write_json(doc_out / "attachments.json", {"attachments": attachment_tree(index)})
    write_report(doc_out / "report.txt", docx, index, doc_out)

    query_matches = None
    if query:
        query_matches = search_index(index, query)
        write_json(doc_out / "query_results.json", {"matches": query_matches})

    node_content = None
    if node_id:
        node = get_node(index, node_id)
        node_content = {
            key: node.get(key)
            for key in ("node_id", "title", "node_type", "text", "start_anchor", "end_anchor", "token_estimate")
        }
        write_json(doc_out / "node_content.json", node_content)

    return {
        "source_file": str(docx),
        "output_dir": str(doc_out),
        "nodes": len(index["nodes"]),
        "anchors": len(index["anchor_map"]),
        "structure_tokens": structure_tokens(index),
        "document_structure_mode": document_mode(structure_tokens(index)),
        "query_matches": len(query_matches) if query_matches is not None else None,
        "node_content_written": node_content is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a DOCX DocumentIndex and write inspection artifacts. "
            "Use one command for normal experiments."
        )
    )
    parser.add_argument("input", type=Path, help="DOCX file, or a directory when --batch is set.")
    parser.add_argument("--out", type=Path, default=Path("outputs/docx_index"), help="Output directory.")
    parser.add_argument("--batch", action="store_true", help="Process all DOCX files under an input directory.")
    parser.add_argument("--query", action="append", default=[], help="Optional keyword to search after building.")
    parser.add_argument("--node-id", help="Optional node_id to expand after building.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        files = iter_docx_inputs(args.input, args.batch)
        if not files:
            raise ValueError(f"no docx files found: {args.input}")
        summaries = [write_document_outputs(path, args.out, args.query, args.node_id) for path in files]
        write_json(args.out / "summary.json", {"documents": summaries})
        print(json.dumps({"documents": summaries}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
