from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docx_retrieval import build_document_index, load_index, write_json
from docx_retrieval.llm import LLMClient, LLMSettings
from docx_retrieval.output import title_rows
from docx_retrieval.retrieval import content_view, keyword_search, llm_query, structure_summary
from docx_retrieval.vector import (
    EmbeddingClient,
    EmbeddingSettings,
    build_vector_index,
    load_vector_index,
    save_vector_index,
    vector_search,
)


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


def command_query(args: argparse.Namespace) -> int:
    data = load_index(args.index)
    settings = LLMSettings.from_sources(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        config_path=args.config,
    )
    result = {
        "matches": llm_query(
            data,
            args.query,
            LLMClient(settings),
            args.cache_dir,
        )
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_build_vector(args: argparse.Namespace) -> int:
    index_path = _resolve_index_path(args)
    data = load_index(index_path)
    settings = EmbeddingSettings.from_sources(
        model=args.embedding_model,
        base_url=args.embedding_base_url,
        api_key=args.embedding_api_key,
        config_path=args.config,
    )
    vector_index = build_vector_index(data, EmbeddingClient(settings), source_index=index_path.name)
    out = args.out or _resolve_vector_path(args, must_exist=False)
    save_vector_index(out, vector_index)
    print(f"wrote: {out}")
    print(f"vector_items={len(vector_index.items)} embedding_model={vector_index.embedding_model}")
    return 0


def command_vector_search(args: argparse.Namespace) -> int:
    index_path = _resolve_index_path(args)
    vector_path = _resolve_vector_path(args, must_exist=True)
    data = load_index(index_path)
    vector_index = load_vector_index(vector_path)
    settings = EmbeddingSettings.from_sources(
        model=args.embedding_model or vector_index.embedding_model,
        base_url=args.embedding_base_url,
        api_key=args.embedding_api_key,
        config_path=args.config,
    )
    matches = []
    for query in args.query:
        matches.extend(vector_search(data, vector_index, query, EmbeddingClient(settings), top_k=args.top_k))
    print(json.dumps({"matches": matches}, ensure_ascii=False, indent=2))
    return 0


def command_ask(args: argparse.Namespace) -> int:
    index_path = _resolve_index_path(args)
    data = load_index(index_path)
    llm_settings = LLMSettings.from_sources(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        config_path=args.config,
    )
    structure_matches = llm_query(data, args.query, LLMClient(llm_settings), args.cache_dir)
    vector_matches = []
    if args.fallback_vector:
        vector_path = _resolve_vector_path(args, must_exist=False)
        if not vector_path.exists():
            if not args.auto_vector:
                raise FileNotFoundError(f"vector_index.json not found: {vector_path}. Use --auto-vector or build-vector first.")
            embedding_settings = EmbeddingSettings.from_sources(
                model=args.embedding_model,
                base_url=args.embedding_base_url,
                api_key=args.embedding_api_key,
                config_path=args.config,
            )
            save_vector_index(vector_path, build_vector_index(data, EmbeddingClient(embedding_settings), source_index=index_path.name))
        vector_index = load_vector_index(vector_path)
        embedding_settings = EmbeddingSettings.from_sources(
            model=args.embedding_model or vector_index.embedding_model,
            base_url=args.embedding_base_url,
            api_key=args.embedding_api_key,
            config_path=args.config,
        )
        for query in args.query:
            vector_matches.extend(vector_search(data, vector_index, query, EmbeddingClient(embedding_settings), top_k=args.top_k))
    print(
        json.dumps(
            {
                "structure_matches": structure_matches,
                "vector_matches": vector_matches,
                "merged_matches": _merge_matches(structure_matches, vector_matches),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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

    query = sub.add_parser("query", help="Use LLM to select relevant nodes from a persisted index structure tree.")
    query.add_argument("--index", type=Path, required=True)
    query.add_argument("--query", action="append", required=True)
    query.add_argument("--model")
    query.add_argument("--base-url")
    query.add_argument("--api-key")
    query.add_argument("--config", type=Path)
    query.add_argument("--cache-dir", type=Path, default=Path("outputs/docx_index_cache"))
    query.set_defaults(func=command_query)

    build_vector = sub.add_parser("build-vector", help="Build vector_index.json from a persisted document index.")
    _add_doc_or_index_args(build_vector)
    build_vector.add_argument("--out", type=Path)
    _add_embedding_args(build_vector)
    build_vector.set_defaults(func=command_build_vector)

    vector = sub.add_parser("vector-search", help="Search vector_index.json and return existing document node ids.")
    _add_doc_or_index_args(vector)
    vector.add_argument("--vector-index", type=Path)
    vector.add_argument("--query", action="append", required=True)
    vector.add_argument("--top-k", type=int, default=8)
    _add_embedding_args(vector)
    vector.set_defaults(func=command_vector_search)

    ask = sub.add_parser("ask", help="Run LLM structure query, optionally with vector fallback, using a document output directory.")
    _add_doc_or_index_args(ask)
    ask.add_argument("--query", action="append", required=True)
    ask.add_argument("--fallback-vector", action="store_true")
    ask.add_argument("--auto-vector", action="store_true")
    ask.add_argument("--vector-index", type=Path)
    ask.add_argument("--top-k", type=int, default=8)
    ask.add_argument("--model")
    ask.add_argument("--base-url")
    ask.add_argument("--api-key")
    ask.add_argument("--cache-dir", type=Path, default=Path("outputs/docx_index_cache"))
    _add_embedding_args(ask)
    ask.set_defaults(func=command_ask)

    titles = sub.add_parser("titles", help="Print title-like nodes.")
    titles.add_argument("--index", type=Path, required=True)
    titles.set_defaults(func=command_titles)

    return parser


def _add_doc_or_index_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc", type=Path, help="Document output directory containing document_index.json.")
    group.add_argument("--index", type=Path, help="Path to document_index.json.")


def _add_embedding_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--embedding-model")
    parser.add_argument("--embedding-base-url")
    parser.add_argument("--embedding-api-key")
    parser.add_argument("--config", type=Path)


def _resolve_index_path(args: argparse.Namespace) -> Path:
    if getattr(args, "index", None):
        return args.index
    return args.doc / "document_index.json"


def _resolve_vector_path(args: argparse.Namespace, must_exist: bool) -> Path:
    if getattr(args, "vector_index", None):
        path = args.vector_index
    elif getattr(args, "doc", None):
        path = args.doc / "vector_index.json"
    else:
        path = args.index.parent / "vector_index.json"
    if must_exist and not path.exists():
        raise FileNotFoundError(f"vector_index.json not found: {path}")
    return path


def _merge_matches(structure_matches: list[dict], vector_matches: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for source, matches in (("structure", structure_matches), ("vector", vector_matches)):
        for match in matches:
            node_id = match.get("node_id")
            if not node_id or node_id in seen:
                continue
            item = dict(match)
            item["source"] = source
            merged.append(item)
            seen.add(node_id)
    return merged


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
