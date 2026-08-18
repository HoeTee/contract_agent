from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from docx_retrieval import build_document_index
from docx_retrieval.evaluation import iter_docx_inputs
from docx_retrieval.indexing import document_mode
from docx_retrieval.llm import LLMClient, LLMSettings
from docx_retrieval.output import attachment_tree, structure_tokens, title_rows, token_rows, write_csv, write_json, write_report
from docx_retrieval.output.writers import load_index
from docx_retrieval.retrieval import (
    RetrievalConfig,
    build_content_context,
    content_view,
    keyword_search,
    llm_query,
    rerank_matches,
)
from docx_retrieval.utils import TimingCollector
from docx_retrieval.vector import EmbeddingClient, EmbeddingSettings, build_vector_index, load_vector_index, save_vector_index, vector_search


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


def write_document_outputs(
    docx: Path,
    root_out: Path,
    query: list[str],
    query_mode: str,
    node_id: str | None,
    llm_expand: bool,
    llm_summary: bool,
    llm_settings: LLMSettings | None,
    build_vector: bool,
    embedding_settings: EmbeddingSettings | None,
    timer: TimingCollector | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    with _stage(timer, "build.document_index_total"):
        index = build_document_index(
            docx,
            llm_expand=llm_expand,
            llm_summary=llm_summary,
            llm_settings=llm_settings,
            cache_dir=root_out / ".cache",
            timer=timer,
        ).to_json_dict()
    doc_out = root_out / safe_name(docx)
    doc_out.mkdir(parents=True, exist_ok=True)

    with _stage(timer, "build.write_outputs"):
        write_json(doc_out / "document_index.json", index)
        write_json(doc_out / "structure_tree.json", index["structure_tree"])
        write_json(doc_out / "titles.json", {"titles": title_rows(index)})
        write_csv(doc_out / "node_tokens.csv", token_rows(index))
        write_json(doc_out / "attachments.json", {"attachments": attachment_tree(index)})
        write_report(doc_out / "report.txt", docx, index, doc_out)

    vector_items = None
    if build_vector:
        with _stage(timer, "build.vector_build"):
            if embedding_settings is None:
                embedding_settings = EmbeddingSettings.from_sources()
            vector_index = build_vector_index(index, EmbeddingClient(embedding_settings))
            vector_items = len(vector_index.items)
            save_vector_index(doc_out / "vector_index.json", vector_index)

    query_matches = None
    if query:
        with _stage(timer, "build.inline_query"):
            if query_mode == "llm":
                if llm_settings is None:
                    llm_settings = LLMSettings.from_sources()
                query_matches = llm_query(index, query, LLMClient(llm_settings), root_out / ".cache")
            else:
                query_matches = search_index(index, query)
            write_json(doc_out / "query_results.json", {"matches": query_matches})

    node_content = None
    if node_id:
        with _stage(timer, "build.inline_content"):
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
        "vector_items": vector_items,
        "elapsed_seconds": round(time.perf_counter() - start_time, 3),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DOCX structure retrieval experiment CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build document_index.json from a DOCX file or directory.")
    build.add_argument("input", type=Path, help="DOCX file, or a directory when --batch is set.")
    build.add_argument("--out", type=Path, default=Path("outputs/docx_index"), help="Output directory.")
    build.add_argument("--batch", action="store_true", help="Process all DOCX files under an input directory.")
    build.add_argument("--vector", action="store_true", help="Also build vector_index.json.")
    _add_llm_args(build)
    _add_embedding_args(build)
    build.add_argument("--llm-expand", action="store_true", help="Use LLM to discover subsection headings in oversized leaf nodes.")
    build.add_argument("--llm-summary", action="store_true", help="Use LLM to generate final node summaries.")
    build.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    build.set_defaults(func=command_build)

    ask = sub.add_parser("ask", help="Retrieve review context from an existing document output directory.")
    ask.add_argument("--doc", type=Path, required=True, help="Document output directory containing document_index.json.")
    ask.add_argument("--query", action="append", required=True)
    ask.add_argument("--part", type=int, default=1, help="Content page number when selected node text exceeds the token budget.")
    ask.add_argument("--input-tokens", type=int, help="Override retrieval.input_tokens.")
    ask.add_argument("--no-vector", action="store_true", help="Disable vector fallback for this request.")
    ask.add_argument("--no-rerank", action="store_true", help="Disable rerank for this request.")
    ask.add_argument("--debug", action="store_true", help="Include internal structure/vector/rerank retrieval details.")
    ask.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    ask.add_argument("--retrieval-config", type=Path, help="Optional docx_retrieval_cli config.yaml path.")
    _add_llm_args(ask)
    _add_embedding_args(ask)
    ask.set_defaults(func=command_ask)

    content = sub.add_parser("content", help="Expand one node's original text.")
    content.add_argument("--doc", type=Path, required=True)
    content.add_argument("--node", required=True)
    content.set_defaults(func=command_content)

    search = sub.add_parser("search", help="Keyword search without model calls.")
    search.add_argument("--doc", type=Path, required=True)
    search.add_argument("--keyword", action="append", required=True)
    search.set_defaults(func=command_search)

    vector = sub.add_parser("vector-search", help="Vector search against vector_index.json.")
    vector.add_argument("--doc", type=Path, required=True)
    vector.add_argument("--query", action="append", required=True)
    vector.add_argument("--input-tokens", type=int)
    vector.add_argument("--retrieval-config", type=Path)
    vector.add_argument("--config", type=Path, help="Optional project config.yaml path for embedding settings.")
    vector.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    _add_embedding_args(vector)
    vector.set_defaults(func=command_vector_search)
    return parser


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", help="OpenAI-compatible model name. Defaults to .env LLM_MODEL_NAME, then config.yaml llm.name.")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL. Defaults to .env LLM_BASE, then config.yaml llm.base_url.")
    parser.add_argument("--api-key", help="API key. Defaults to .env LLM_API_KEY, then OPENAI_API_KEY/CHATGPT_API_KEY/LLM_API_KEY.")
    parser.add_argument("--config", type=Path, help="Optional project config.yaml path for LLM/embedding settings.")


def _add_embedding_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--embedding-model", help="Embedding model name. Defaults to .env EMBEDDING_MODEL_NAME.")
    parser.add_argument("--embedding-base-url", help="Embedding OpenAI-compatible base URL. Defaults to .env EMBEDDING_BASE.")
    parser.add_argument("--embedding-api-key", help="Embedding API key. Defaults to .env EMBED_API_KEY.")


def command_build(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    timer = TimingCollector(enabled=not args.quiet)
    with timer.stage("build.discover_inputs"):
        files = iter_docx_inputs(args.input, args.batch)
    if not files:
        raise ValueError(f"no docx files found: {args.input}")
    llm_settings = None
    embedding_settings = None
    if args.llm_expand or args.llm_summary:
        with timer.stage("build.load_llm_settings"):
            llm_settings = LLMSettings.from_sources(
                model=args.model,
                base_url=args.base_url,
                api_key=args.api_key,
                config_path=args.config,
            )
    if args.vector:
        with timer.stage("build.load_embedding_settings"):
            embedding_settings = EmbeddingSettings.from_sources(
                model=args.embedding_model,
                base_url=args.embedding_base_url,
                api_key=args.embedding_api_key,
                config_path=args.config,
            )
    summaries = [
        write_document_outputs(
            path,
            args.out,
            [],
            "llm",
            None,
            args.llm_expand,
            args.llm_summary,
            llm_settings,
            args.vector,
            embedding_settings,
            timer,
        )
        for path in files
    ]
    total_elapsed = round(time.perf_counter() - start_time, 3)
    with timer.stage("build.write_summary"):
        write_json(args.out / "summary.json", {"documents": summaries, "total_elapsed_seconds": total_elapsed})
    if not args.quiet:
        print(f"[timing] build.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    print(json.dumps({"documents": summaries, "total_elapsed_seconds": total_elapsed}, ensure_ascii=False, indent=2))
    return 0


def command_ask(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    timer = TimingCollector(enabled=not args.quiet)
    with timer.stage("ask.load_config"):
        config = RetrievalConfig.from_sources(
            config_path=args.retrieval_config,
            input_tokens=args.input_tokens,
            vector_enabled=False if args.no_vector else None,
            rerank_enabled=False if args.no_rerank else None,
        )
    index_path = _index_path(args.doc)
    with timer.stage("ask.load_index"):
        data = load_index(index_path)
    with timer.stage("ask.load_llm_settings"):
        llm_settings = LLMSettings.from_sources(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            config_path=args.config,
        )
    with timer.stage("ask.init_llm_client"):
        llm_client = LLMClient(llm_settings)
    with timer.stage("ask.llm_structure_query"):
        structure_matches = llm_query(data, args.query, llm_client, args.doc / ".cache", input_tokens=config.input_tokens)
    vector_matches = []
    if config.vector.enabled:
        vector_path = args.doc / "vector_index.json"
        if not vector_path.exists():
            if not config.vector.auto_build:
                raise FileNotFoundError(f"vector_index.json not found: {vector_path}")
            with timer.stage("ask.auto_build_vector_index"):
                embedding_settings = EmbeddingSettings.from_sources(
                    model=args.embedding_model,
                    base_url=args.embedding_base_url,
                    api_key=args.embedding_api_key,
                    config_path=args.config,
                )
                save_vector_index(vector_path, build_vector_index(data, EmbeddingClient(embedding_settings), source_index=index_path.name))
        with timer.stage("ask.load_vector_index"):
            vector_index = load_vector_index(vector_path)
        with timer.stage("ask.load_embedding_settings"):
            embedding_settings = EmbeddingSettings.from_sources(
                model=args.embedding_model or vector_index.embedding_model,
                base_url=args.embedding_base_url,
                api_key=args.embedding_api_key,
                config_path=args.config,
            )
        with timer.stage("ask.init_embedding_client"):
            embedding_client = EmbeddingClient(embedding_settings)
        with timer.stage("ask.vector_search"):
            for query in args.query:
                vector_matches.extend(
                    vector_search(
                        data,
                        vector_index,
                        query,
                        embedding_client,
                        score_threshold=config.vector.score_threshold,
                        input_tokens=config.input_tokens,
                    )
                )
    with timer.stage("ask.merge_matches"):
        candidates = _merge_matches(structure_matches, vector_matches)
    query_text = "\n".join(args.query)
    if config.rerank.enabled:
        with timer.stage("ask.rerank"):
            ranked_matches = rerank_matches(data, query_text, candidates, llm_client, config.input_tokens, args.doc / ".cache")
    else:
        ranked_matches = candidates
    with timer.stage("ask.build_content_context"):
        context = build_content_context(data, ranked_matches, config.input_tokens, part=args.part)
    total_elapsed = round(time.perf_counter() - start_time, 3)
    if not args.quiet:
        print(f"[timing] ask.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    payload = {
        "query": args.query if len(args.query) > 1 else args.query[0],
        "nodes": context["content_context"],
        "elapsed_seconds": total_elapsed,
    }
    if args.debug:
        payload["debug"] = {
            "ranked_matches": ranked_matches,
            "structure_matches": structure_matches,
            "vector_matches": vector_matches,
            "pagination": context["pagination"],
            "budget": context["budget"],
            "timings": timer.as_dict(),
        }
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_content(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    result = content_view(load_index(_index_path(args.doc)), args.node)
    result["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_search(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    result = keyword_search(load_index(_index_path(args.doc)), args.keyword)
    payload = result.model_dump(mode="json")
    payload["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_vector_search(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    timer = TimingCollector(enabled=not args.quiet)
    with timer.stage("vector_search.load_config"):
        config = RetrievalConfig.from_sources(config_path=args.retrieval_config, input_tokens=args.input_tokens)
    with timer.stage("vector_search.load_index"):
        data = load_index(_index_path(args.doc))
    with timer.stage("vector_search.load_vector_index"):
        vector_index = load_vector_index(args.doc / "vector_index.json")
    with timer.stage("vector_search.load_embedding_settings"):
        settings = EmbeddingSettings.from_sources(
            model=args.embedding_model or vector_index.embedding_model,
            base_url=args.embedding_base_url,
            api_key=args.embedding_api_key,
            config_path=args.config,
        )
    matches = []
    with timer.stage("vector_search.query_embedding_and_rank"):
        embedding_client = EmbeddingClient(settings)
        for query in args.query:
            matches.extend(
                vector_search(
                    data,
                    vector_index,
                    query,
                    embedding_client,
                    score_threshold=config.vector.score_threshold,
                    input_tokens=config.input_tokens,
                )
            )
    total_elapsed = round(time.perf_counter() - start_time, 3)
    if not args.quiet:
        print(f"[timing] vector_search.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    print(json.dumps({"matches": matches, "elapsed_seconds": total_elapsed}, ensure_ascii=False, indent=2))
    return 0


def _index_path(doc_dir: Path) -> Path:
    return doc_dir / "document_index.json"


def _merge_matches(structure_matches: list[dict], vector_matches: list[dict]) -> list[dict]:
    merged: dict[str, dict[str, Any]] = {}
    for source, matches in (("structure", structure_matches), ("vector", vector_matches)):
        for match in matches:
            node_id = match.get("node_id")
            if not node_id:
                continue
            item = merged.setdefault(node_id, dict(match))
            sources = set(item.get("sources") or [])
            sources.add(source)
            item["sources"] = sorted(sources)
            if source == "vector":
                item["vector_score"] = match.get("score")
            if source == "structure":
                item["structure_reason"] = match.get("reason")
    return list(merged.values())


def _stage(timer: TimingCollector | None, name: str):
    if timer is None:
        from contextlib import nullcontext

        return nullcontext()
    return timer.stage(name)


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
