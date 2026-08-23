from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent

# Keep stdout machine-readable even when shared project modules print during import.
with contextlib.redirect_stdout(sys.stderr):
    from docxindex import build_document_index
    from docxindex.evaluation import iter_docx_inputs
    from docxindex.indexing.config import IndexingConfig
    from docxindex.indexing import document_mode
    from docxindex.llm import LLMClient, LLMSettings
    from docxindex.output import attachment_tree, structure_tokens, title_rows, token_rows, write_csv, write_json, write_report
    from docxindex.output.writers import load_index
    from docxindex.retrieval import (
        RetrievalConfig,
        RouteConfig,
        build_content_context,
        content_view,
        join_matches,
        keyword_search,
        llm_query,
        plan_route,
        region_matches,
        rerank_matches,
        rule_matches,
        scan_matches,
        title_matches,
    )
    from docxindex.utils import RunLogger, TimingCollector
    from docxindex.vector import EmbeddingClient, EmbeddingSettings, build_vector_index, load_vector_index, save_vector_index, vector_search

DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "index"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs"


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


def docxindex_structure(index: dict[str, Any], docx: Path) -> dict[str, Any]:
    return {
        "schema_version": "docxindex-v3",
        "doc_name": docx.name,
        "doc_title": _doc_title(index, docx),
        "structure": index["structure_tree"],
    }


def content_store(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node["node_id"]: {
            "node_id": node["node_id"],
            "title": node.get("title"),
            "node_type": node.get("node_type"),
            "text": node.get("text") or "",
            "summary": node.get("summary") or "",
            "start_index": node.get("start_index"),
            "end_index": node.get("end_index"),
            "start_anchor": node.get("start_anchor"),
            "end_anchor": node.get("end_anchor"),
            "token_estimate": node.get("token_estimate"),
            "nodes": node.get("nodes") or node.get("children") or [],
            "table_id": node.get("table_id"),
            "mapping_ref": node.get("mapping_ref"),
            "row_start": node.get("row_start"),
            "row_end": node.get("row_end"),
        }
        for node in index.get("nodes") or []
    }


def anchor_store(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        anchor_id: {"anchor_id": anchor_id, **record}
        for anchor_id, record in (index.get("anchor_map") or {}).items()
    }


def manifest_index(index: dict[str, Any], docx: Path) -> dict[str, Any]:
    return {
        "schema_version": "docxindex-v3",
        "source_file": str(docx),
        "doc_name": docx.name,
        "doc_title": _doc_title(index, docx),
        "top_regions": index.get("top_regions") or {},
        "settings": index.get("settings") or {},
        "files": {
            "structure_tree": "structure_tree.json",
            "content_store": "content_store.json",
            "anchor_store": "anchor_store.json",
            "table_store": "table_store.json",
            "vector_index": "vector_index.json",
        },
        "stats": {
            "node_count": len(index.get("nodes") or []),
            "anchor_count": len(index.get("anchor_map") or {}),
            "table_count": len(index.get("table_map") or {}),
            "structure_tokens": structure_tokens(index),
        },
    }


def _doc_title(index: dict[str, Any], docx: Path) -> str:
    for node in index.get("nodes") or []:
        if node.get("node_id") == "frontmatter":
            lines = [line.strip() for line in (node.get("text") or "").splitlines() if line.strip()]
            for line in lines:
                if "合同" in line and len(line) <= 80:
                    return line
            if lines:
                return lines[0][:80]
    return docx.stem


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
    use_cache: bool = True,
    llm_concurrency: int = 10,
    embedding_concurrency: int = 10,
    paragraph_split_threshold_tokens: int = 1000,
    paragraph_chunk_target_tokens: int = 700,
    table_split_threshold_tokens: int = 20000,
    table_chunk_target_tokens: int = 18000,
    heading_profiles: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    start_time = time.perf_counter()
    cache_dir = root_out / ".cache" if use_cache else None
    with _stage(timer, "build.document_index_total"):
        index = build_document_index(
            docx,
            llm_expand=llm_expand,
            llm_summary=llm_summary,
            llm_settings=llm_settings,
            cache_dir=cache_dir,
            timer=timer,
            llm_concurrency=llm_concurrency,
            paragraph_split_threshold_tokens=paragraph_split_threshold_tokens,
            paragraph_chunk_target_tokens=paragraph_chunk_target_tokens,
            table_split_threshold_tokens=table_split_threshold_tokens,
            table_chunk_target_tokens=table_chunk_target_tokens,
            heading_profiles=heading_profiles,
        ).to_json_dict()
    doc_out = root_out / safe_name(docx)
    doc_out.mkdir(parents=True, exist_ok=True)

    with _stage(timer, "build.write_outputs"):
        structure_doc = docxindex_structure(index, docx)
        content_doc = content_store(index)
        anchor_doc = anchor_store(index)
        table_doc = index.get("table_map") or {}
        manifest = manifest_index(index, docx)
        write_json(doc_out / "document_index.json", manifest)
        write_json(doc_out / "structure_tree.json", structure_doc)
        write_json(doc_out / "content_store.json", content_doc)
        write_json(doc_out / "anchor_store.json", anchor_doc)
        write_json(doc_out / "table_store.json", table_doc)
        write_json(doc_out / "titles.json", {"titles": title_rows(index)})
        write_csv(doc_out / "node_tokens.csv", token_rows(index))
        write_json(doc_out / "attachments.json", {"attachments": attachment_tree(index)})
        write_report(doc_out / "report.txt", docx, index, doc_out)

    vector_items = None
    if build_vector:
        with _stage(timer, "build.vector_build"):
            if embedding_settings is None:
                embedding_settings = EmbeddingSettings.from_sources()
            vector_index = build_vector_index(index, EmbeddingClient(embedding_settings), concurrency=embedding_concurrency)
            vector_items = len(vector_index.items)
            save_vector_index(doc_out / "vector_index.json", vector_index)

    query_matches = None
    if query:
        with _stage(timer, "build.inline_query"):
            if query_mode == "llm":
                if llm_settings is None:
                    llm_settings = LLMSettings.from_sources()
                query_matches = llm_query(
                    index,
                    query,
                    LLMClient(llm_settings),
                    cache_dir,
                    timer=timer,
                    concurrency=llm_concurrency,
                )
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
    parser = argparse.ArgumentParser(description="docxindex contract structure indexing and retrieval CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build document_index.json from a DOCX file or directory.")
    build.add_argument("input", type=Path, help="DOCX file, or a directory when --batch is set.")
    build.add_argument("--out", type=_project_local_path, default=DEFAULT_OUTPUT_DIR, help="Output directory. Relative paths are resolved under this CLI project.")
    build.add_argument("--batch", action="store_true", help="Process all DOCX files under an input directory.")
    build.add_argument("--no-vector", action="store_true", help="Do not build vector_index.json.")
    _add_llm_args(build)
    _add_embedding_args(build)
    build.add_argument("--no-llm-expand", action="store_true", help="Disable LLM subsection discovery for oversized leaf nodes.")
    build.add_argument("--no-llm-summary", action="store_true", help="Disable LLM final node summaries.")
    build.add_argument("--no-cache", action="store_true", help="Disable LLM response cache for expand/summary/query stages.")
    build.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    build.add_argument("--retrieval-config", type=Path, help="Optional docxindex config.yaml path.")
    _add_log_args(build)
    build.set_defaults(func=command_build)

    ask = sub.add_parser("ask", help="Retrieve review context from an existing document output directory.")
    ask.add_argument("--doc", type=_project_local_path, required=True, help="Document output directory containing document_index.json.")
    ask.add_argument("--query", action="append", required=True)
    ask.add_argument("--part", type=int, default=1, help="Content page number when selected node text exceeds the token budget.")
    ask.add_argument("--all-parts", action="store_true", help="Return every content page in one run for evaluation or batch processing.")
    ask.add_argument("--input-tokens", type=int, help="Override retrieval.input_tokens.")
    ask.add_argument("--no-vector", action="store_true", help="Disable vector fallback for this request.")
    ask.add_argument("--no-rerank", action="store_true", help="Disable rerank for this request.")
    ask.add_argument("--debug", action="store_true", help="Include internal structure/vector/rerank retrieval details.")
    ask.add_argument("--no-cache", action="store_true", help="Disable LLM response cache for structure query and rerank.")
    ask.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    ask.add_argument("--retrieval-config", type=Path, help="Optional docxindex config.yaml path.")
    _add_llm_args(ask)
    _add_embedding_args(ask)
    _add_log_args(ask)
    ask.set_defaults(func=command_ask)

    content = sub.add_parser("content", help="Expand one node's original text.")
    content.add_argument("--doc", type=_project_local_path, required=True)
    content.add_argument("--node", required=True)
    _add_log_args(content)
    content.set_defaults(func=command_content)

    search = sub.add_parser("search", help="Keyword search without model calls.")
    search.add_argument("--doc", type=_project_local_path, required=True)
    search.add_argument("--keyword", action="append", required=True)
    _add_log_args(search)
    search.set_defaults(func=command_search)

    vector = sub.add_parser("vector-search", help="Vector search against vector_index.json.")
    vector.add_argument("--doc", type=_project_local_path, required=True)
    vector.add_argument("--query", action="append", required=True)
    vector.add_argument("--input-tokens", type=int)
    vector.add_argument("--retrieval-config", type=Path)
    vector.add_argument("--config", type=Path, help="Optional project config.yaml path for embedding settings.")
    vector.add_argument("--quiet", action="store_true", help="Do not print stage timings to stderr.")
    _add_embedding_args(vector)
    _add_log_args(vector)
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


def _add_log_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--log-dir", type=_project_local_path, default=DEFAULT_LOG_DIR, help="Local directory for CLI run logs. Relative paths are resolved under this CLI project.")
    parser.add_argument("--no-log", action="store_true", help="Disable local file logging for this command.")


def _project_local_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (PROJECT_DIR / path).resolve()


def command_build(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    logger = _logger(args)
    timer = TimingCollector(enabled=not args.quiet, log_stream=logger.stream if logger else None)
    use_llm_expand = not args.no_llm_expand
    use_llm_summary = not args.no_llm_summary
    use_vector = not args.no_vector
    with timer.stage("build.load_retrieval_config"):
        retrieval_config = RetrievalConfig.from_sources(config_path=args.retrieval_config)
        indexing_config = IndexingConfig.from_sources(config_path=args.retrieval_config)
        timer.note("build.concurrency.llm", retrieval_config.concurrency.llm)
        timer.note("build.concurrency.embedding", retrieval_config.concurrency.embedding)
        timer.note("build.concurrency.reranker", retrieval_config.concurrency.reranker)
    with timer.stage("build.discover_inputs"):
        files = iter_docx_inputs(args.input, args.batch)
    if not files:
        raise ValueError(f"no docx files found: {args.input}")
    llm_settings = None
    embedding_settings = None
    if use_llm_expand or use_llm_summary:
        with timer.stage("build.load_llm_settings"):
            llm_settings = LLMSettings.from_sources(
                model=args.model,
                base_url=args.base_url,
                api_key=args.api_key,
                config_path=args.config,
            )
    if use_vector:
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
            use_llm_expand,
            use_llm_summary,
            llm_settings,
            use_vector,
            embedding_settings,
            timer,
            use_cache=not args.no_cache,
            llm_concurrency=retrieval_config.concurrency.llm,
            embedding_concurrency=retrieval_config.concurrency.embedding,
            paragraph_split_threshold_tokens=indexing_config.paragraph.split_threshold_tokens,
            paragraph_chunk_target_tokens=indexing_config.paragraph.chunk_target_tokens,
            table_split_threshold_tokens=indexing_config.table.split_threshold_tokens,
            table_chunk_target_tokens=indexing_config.table.chunk_target_tokens,
            heading_profiles=indexing_config.heading.compile_profiles(),
        )
        for path in files
    ]
    total_elapsed = round(time.perf_counter() - start_time, 3)
    with timer.stage("build.write_summary"):
        write_json(args.out / "summary.json", {"documents": summaries, "total_elapsed_seconds": total_elapsed})
    if not args.quiet:
        print(f"[timing] build.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    payload = {"documents": summaries, "total_elapsed_seconds": total_elapsed}
    _log_json(args, "result", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_ask(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    logger = _logger(args)
    timer = TimingCollector(enabled=not args.quiet, log_stream=logger.stream if logger else None)
    with timer.stage("ask.load_config"):
        config = RetrievalConfig.from_sources(
            config_path=args.retrieval_config,
            input_tokens=args.input_tokens,
            vector_enabled=False if args.no_vector else None,
            rerank_enabled=False if args.no_rerank else None,
        )
        timer.note("ask.concurrency.llm", config.concurrency.llm)
        timer.note("ask.concurrency.embedding", config.concurrency.embedding)
        timer.note("ask.concurrency.reranker", config.concurrency.reranker)
        route_config = RouteConfig.load(args.retrieval_config)
    index_path = _index_path(args.doc)
    with timer.stage("ask.load_index"):
        data = load_runtime_index(args.doc)
    with timer.stage("ask.load_llm_settings"):
        llm_settings = LLMSettings.from_sources(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            config_path=args.config,
        )
    with timer.stage("ask.init_llm_client"):
        llm_client = LLMClient(llm_settings)
    query_text = "\n".join(args.query)
    cache_dir = args.doc / ".cache" if not args.no_cache else None
    with timer.stage("ask.route"):
        route_plan = plan_route(data, query_text, llm_client, route_config, cache_dir)
        routed_matches = _execute_route(data, query_text, route_plan)

    structure_matches: list[dict[str, Any]] = []
    vector_matches: list[dict[str, Any]] = []
    fallback_used = not routed_matches or (
        route_config.fallback_enabled and route_plan.fallback and not _route_is_complete(route_plan)
    )
    if fallback_used:
        with timer.stage("ask.llm_structure_query"):
            structure_matches = llm_query(
                data,
                args.query,
                llm_client,
                cache_dir,
                input_tokens=config.input_tokens,
                timer=timer,
                concurrency=config.concurrency.llm,
            )[: route_config.llm_candidates]
    if fallback_used and config.vector.enabled:
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
                save_vector_index(
                    vector_path,
                    build_vector_index(
                        data,
                        EmbeddingClient(embedding_settings),
                        source_index=index_path.name,
                        concurrency=config.concurrency.embedding,
                    ),
                )
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
                        score_threshold=route_config.vector_threshold,
                        input_tokens=config.input_tokens,
                        concurrency=config.concurrency.embedding,
                    )[: route_config.vector_candidates]
                )
    with timer.stage("ask.merge_matches"):
        fallback_matches = _merge_matches(structure_matches, vector_matches)
        candidates = _merge_routed_matches(routed_matches, fallback_matches)
    if fallback_used and config.rerank.enabled:
        with timer.stage("ask.rerank"):
            rerank_cache_dir = args.doc / ".cache" if not args.no_cache else None
            ranked_matches = rerank_matches(
                data,
                query_text,
                candidates,
                llm_client,
                config.input_tokens,
                rerank_cache_dir,
                concurrency=config.concurrency.reranker,
            )
        ranked_matches = ranked_matches[: route_config.max_nodes]
    else:
        ranked_matches = candidates
    with timer.stage("ask.build_content_context"):
        content_budget = (
            config.scan_batch_tokens
            if any(step.method == "scan" for step in route_plan.steps)
            else config.output_tokens
        )
        context = build_content_context(data, ranked_matches, content_budget, part=args.part)
        if args.all_parts:
            all_nodes = list(context["content_context"])
            part = args.part
            while context["pagination"]["has_more"]:
                part += 1
                context = build_content_context(data, ranked_matches, content_budget, part=part)
                all_nodes.extend(context["content_context"])
            context["content_context"] = all_nodes
    total_elapsed = round(time.perf_counter() - start_time, 3)
    if not args.quiet:
        print(f"[timing] ask.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    payload = {
        "query": args.query if len(args.query) > 1 else args.query[0],
        "mode": [step.method for step in route_plan.steps],
        "nodes": context["content_context"],
        "elapsed_seconds": total_elapsed,
    }
    if not args.all_parts and context["pagination"]["has_more"]:
        payload["next_part"] = context["pagination"]["next_part"]
    if args.debug:
        payload["debug"] = {
            "ranked_matches": ranked_matches,
            "structure_matches": structure_matches,
            "vector_matches": vector_matches,
            "route_plan": route_plan.model_dump(mode="json"),
            "routed_matches": routed_matches,
            "fallback_used": fallback_used,
            "pagination": context["pagination"],
            "budget": context["budget"],
            "timings": timer.as_dict(),
        }
    _log_json(
        args,
        "result_summary",
        {
            "elapsed_seconds": total_elapsed,
            "node_count": len(payload["nodes"]),
            "node_ids": [node.get("node_id") for node in payload["nodes"]],
            "timings": timer.as_dict(),
        },
    )
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
    result = content_view(load_runtime_index(args.doc), args.node)
    result["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
    _log_json(args, "result_summary", {"elapsed_seconds": result["elapsed_seconds"], "node_id": result.get("node_id")})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_search(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    result = keyword_search(load_runtime_index(args.doc), args.keyword)
    payload = result.model_dump(mode="json")
    payload["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
    _log_json(args, "result_summary", {"elapsed_seconds": payload["elapsed_seconds"], "match_count": len(payload.get("matches") or [])})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_vector_search(args: argparse.Namespace) -> int:
    start_time = time.perf_counter()
    logger = _logger(args)
    timer = TimingCollector(enabled=not args.quiet, log_stream=logger.stream if logger else None)
    with timer.stage("vector_search.load_config"):
        config = RetrievalConfig.from_sources(config_path=args.retrieval_config, input_tokens=args.input_tokens)
        timer.note("vector_search.concurrency.embedding", config.concurrency.embedding)
    with timer.stage("vector_search.load_index"):
        data = load_runtime_index(args.doc)
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
                    concurrency=config.concurrency.embedding,
                )
            )
    total_elapsed = round(time.perf_counter() - start_time, 3)
    if not args.quiet:
        print(f"[timing] vector_search.total: {total_elapsed:.3f}s", file=sys.stderr, flush=True)
    payload = {"matches": matches, "elapsed_seconds": total_elapsed}
    _log_json(
        args,
        "result_summary",
        {
            "elapsed_seconds": total_elapsed,
            "match_count": len(matches),
            "timings": timer.as_dict(),
        },
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _index_path(doc_dir: Path) -> Path:
    return doc_dir / "document_index.json"


def load_runtime_index(doc_dir: Path) -> dict[str, Any]:
    manifest = load_index(_index_path(doc_dir))
    schema_version = str(manifest.get("schema_version") or "")
    if not schema_version.startswith(("docxindex-v", "docx-pageindex-like-v")):
        return manifest
    files = manifest.get("files") or {}
    structure_doc = load_index(doc_dir / files.get("structure_tree", "structure_tree.json"))
    content_doc = load_index(doc_dir / files.get("content_store", "content_store.json"))
    anchor_doc = load_index(doc_dir / files.get("anchor_store", "anchor_store.json"))
    table_path = doc_dir / files.get("table_store", "table_store.json")
    table_doc = load_index(table_path) if table_path.exists() else {}
    nodes = []
    for node_id, node in content_doc.items():
        item = dict(node)
        item["children"] = item.get("nodes") or []
        nodes.append(item)
    nodes.sort(key=lambda item: ((item.get("start_index") is None), item.get("start_index") or 0, item.get("node_id") or ""))
    return {
        "schema_version": manifest["schema_version"],
        "source_file": manifest.get("source_file"),
        "doc_name": manifest.get("doc_name"),
        "doc_title": manifest.get("doc_title"),
        "top_regions": manifest.get("top_regions") or {},
        "settings": manifest.get("settings") or {},
        "nodes": nodes,
        "root_nodes": [node.get("node_id") for node in structure_doc.get("structure") or []],
        "structure_tree": structure_doc.get("structure") or [],
        "anchor_map": {
            anchor_id: {key: value for key, value in record.items() if key != "anchor_id"}
            for anchor_id, record in anchor_doc.items()
        },
        "table_map": table_doc,
        "files": files,
        "stats": manifest.get("stats") or {},
    }


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


def _execute_route(index: dict[str, Any], query: str, plan: Any) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for step in plan.steps:
        if step.method == "title":
            current = title_matches(index, step)
        elif step.method == "region":
            current = region_matches(index, step, matches)
        elif step.method == "rule":
            current = rule_matches(index, step, query)
        elif step.method == "join":
            current = join_matches(index, query, step)
        elif step.method == "scan":
            current = scan_matches(index)
        else:
            raise ValueError(f"unsupported route method: {step.method}")
        matches = _merge_routed_matches(matches, current)
    return matches


def _route_is_complete(plan: Any) -> bool:
    return any(step.method == "scan" or (step.method == "title" and step.all_titles) for step in plan.steps)


def _merge_routed_matches(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for matches in groups:
        for match in matches:
            node_id = match.get("node_id")
            if not node_id:
                continue
            if node_id not in merged:
                merged[node_id] = dict(match)
                order.append(node_id)
            item = merged[node_id]
            sources = set(item.get("sources") or [])
            sources.update(match.get("sources") or [])
            item["sources"] = sorted(source for source in sources if source)
            for key in ("vector_score", "structure_reason", "reason", "rerank_score", "rerank_reason"):
                if match.get(key) is not None:
                    item[key] = match[key]
    return [merged[node_id] for node_id in order]


def _stage(timer: TimingCollector | None, name: str):
    if timer is None:
        from contextlib import nullcontext

        return nullcontext()
    return timer.stage(name)


def _logger(args: argparse.Namespace) -> RunLogger | None:
    return getattr(args, "_run_logger", None)


def _log_json(args: argparse.Namespace, label: str, payload: Any) -> None:
    logger = _logger(args)
    if logger:
        logger.write_json(label, payload)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = RunLogger(args.command, args.log_dir, enabled=not args.no_log)
    args._run_logger = logger
    if logger.path:
        print(f"[log] {logger.path}", file=sys.stderr, flush=True)
    logger.log_args(args)
    try:
        return args.func(args)
    except Exception as exc:
        logger.log_exception(exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
