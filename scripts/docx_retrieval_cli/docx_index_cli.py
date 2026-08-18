from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx_retrieval import build_document_index, load_index, write_json
from docx_retrieval.llm import LLMSettings
from docx_retrieval.output import title_rows
from docx_retrieval.retrieval import content_view, keyword_search, structure_summary


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def command_build(args: argparse.Namespace) -> int:
    llm_settings = None
    if args.llm_expand or args.llm_summary:
        llm_settings = LLMSettings.from_sources(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            config_path=args.config,
        )
    data = build_document_index(
        args.docx,
        llm_expand=args.llm_expand,
        llm_summary=args.llm_summary,
        llm_settings=llm_settings,
        cache_dir=args.cache_dir,
    ).to_json_dict()
    write_json(args.out, data)
    print(f"wrote: {args.out}")
    print(f"nodes={len(data['nodes'])} anchors={len(data['anchor_map'])}")
    return 0


def command_structure(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    print(json.dumps(structure_summary(data), ensure_ascii=False, indent=2))
    return 0


def command_content(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    print(json.dumps(content_view(data, args.node_id), ensure_ascii=False, indent=2))
    return 0


def command_search(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    print(keyword_search(data, args.keyword).model_dump_json(indent=2))
    return 0


def command_titles(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    print(json.dumps({"titles": title_rows(data)}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect experimental DOCX structure retrieval indexes.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a persistent DocumentIndex JSON from a DOCX file.")
    build.add_argument("--docx", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--llm-expand", action="store_true")
    build.add_argument("--llm-summary", action="store_true")
    build.add_argument("--model")
    build.add_argument("--base-url")
    build.add_argument("--api-key")
    build.add_argument("--config", type=Path)
    build.add_argument("--cache-dir", type=Path, default=Path("outputs/docx_index_cache"))
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
