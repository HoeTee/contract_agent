from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx_retrieval import build_document_index, estimate_tokens, get_node, load_index, write_json
from docx_retrieval.constants import STRUCTURE_INLINE_BUDGET_TOKENS, STRUCTURE_PAGED_BUDGET_TOKENS
from docx_retrieval.retriever import keyword_search


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def command_build(args: argparse.Namespace) -> int:
    data = build_document_index(args.docx)
    write_json(args.out, data)
    print(f"wrote: {args.out}")
    print(f"nodes={len(data['nodes'])} anchors={len(data['anchor_map'])}")
    return 0


def command_structure(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    structure = data["structure_tree"]
    structure_tokens = estimate_tokens(json.dumps(structure, ensure_ascii=False))
    mode = "compact_structure"
    if structure_tokens > STRUCTURE_PAGED_BUDGET_TOKENS:
        mode = "filtered_or_paged_structure"
    elif structure_tokens > STRUCTURE_INLINE_BUDGET_TOKENS:
        mode = "paged_structure"
    print(
        json.dumps(
            {
                "document_structure_mode": mode,
                "structure_tokens": structure_tokens,
                "structure_index": structure,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_content(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    node = get_node(data, args.node_id)
    print(
        json.dumps(
            {
                key: node.get(key)
                for key in ("node_id", "title", "node_type", "text", "start_anchor", "end_anchor", "token_estimate")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_search(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    print(json.dumps({"matches": keyword_search(data, args.keyword)}, ensure_ascii=False, indent=2))
    return 0


def command_titles(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    rows = [
        {
            "node_id": node["node_id"],
            "level": node.get("level"),
            "node_type": node.get("node_type"),
            "title": node.get("title"),
            "token_estimate": node.get("token_estimate"),
            "start_anchor": node.get("start_anchor"),
            "end_anchor": node.get("end_anchor"),
        }
        for node in data["nodes"]
        if node.get("node_type") in {"section", "attachment_parent", "attachment_section", "visual_title", "heading", "plain_label"}
    ]
    print(json.dumps({"titles": rows}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect experimental DOCX structure retrieval indexes.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a persistent DocumentIndex JSON from a DOCX file.")
    build.add_argument("--docx", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.set_defaults(func=command_build)

    structure = sub.add_parser("structure", help="Print the lightweight structure tree.")
    structure.add_argument("--index", type=Path, required=True)
    structure.set_defaults(func=command_structure)

    content = sub.add_parser("content", help="Print one node's original text.")
    content.add_argument("--index", type=Path, required=True)
    content.add_argument("--node-id", required=True)
    content.set_defaults(func=command_content)

    search = sub.add_parser("search", help="Search index title/text by keyword.")
    search.add_argument("--index", type=Path, required=True)
    search.add_argument("--keyword", action="append", required=True)
    search.set_defaults(func=command_search)

    titles = sub.add_parser("titles", help="Print title-like nodes.")
    titles.add_argument("--index", type=Path, required=True)
    titles.set_defaults(func=command_titles)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
