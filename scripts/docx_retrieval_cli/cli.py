from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from docx_retrieval import build_document_index
from docx_retrieval.evaluation import iter_docx_inputs
from docx_retrieval.indexing import document_mode
from docx_retrieval.output import attachment_tree, structure_tokens, title_rows, token_rows, write_csv, write_json, write_report
from docx_retrieval.retrieval import content_view, keyword_search


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def safe_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r'[<>:"/\\|?*\s]+', "_", name).strip("._")
    return name[:120] or "document"


def search_index(index: dict[str, Any], keywords: list[str]) -> list[dict[str, Any]]:
    return [match.model_dump(mode="json") for match in keyword_search(index, keywords).matches]


def write_document_outputs(docx: Path, root_out: Path, query: list[str], node_id: str | None) -> dict[str, Any]:
    index = build_document_index(docx).to_json_dict()
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
        node_content = content_view(index, node_id)
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
