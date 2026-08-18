from __future__ import annotations

from pathlib import Path

from docx_retrieval.llm import LLMClient
from docx_retrieval.llm.cache import JsonlCache, cache_key, text_hash
from docx_retrieval.llm.prompts import SUMMARY_PROMPT_VERSION, summary_prompt
from docx_retrieval.schema import DocumentNode

from .token_budget import SUMMARY_TRIGGER_MIN_TOKENS, estimate_tokens

SUMMARY_INPUT_TARGET_TOKENS = 6000


def summarize_nodes(roots: list[DocumentNode], client: LLMClient, cache_dir: Path | None) -> None:
    cache = JsonlCache(cache_dir / "llm_summary.jsonl" if cache_dir else None)
    for node in roots:
        _summarize_node(node, client, cache)


def _summarize_node(node: DocumentNode, client: LLMClient, cache: JsonlCache) -> str:
    for child in node.children:
        _summarize_node(child, client, cache)
    if node.token_estimate < SUMMARY_TRIGGER_MIN_TOKENS and not node.children:
        return node.summary

    content = _summary_content(node)
    key = cache_key(
        SUMMARY_PROMPT_VERSION,
        client.settings.model,
        node.node_id,
        text_hash(content),
    )
    cached = cache.get(key)
    if cached is None:
        response = client.complete_json(summary_prompt(node.title, node.node_type, content))
        cached = {"summary": str(response.get("summary") or "").strip()}
        cache.set(key, cached)
    if cached.get("summary"):
        node.summary = cached["summary"]
    return node.summary


def _summary_content(node: DocumentNode) -> str:
    if node.children:
        lines = []
        for child in node.children:
            child_summary = child.summary or child.title
            lines.append(f"- {child.title}: {child_summary}")
        return _truncate_by_tokens("\n".join(lines))
    return _truncate_by_tokens(node.text)


def _truncate_by_tokens(text: str) -> str:
    if estimate_tokens(text) <= SUMMARY_INPUT_TARGET_TOKENS:
        return text
    chars = max(1000, int(len(text) * SUMMARY_INPUT_TARGET_TOKENS / max(estimate_tokens(text), 1)))
    return text[:chars].rstrip() + "..."
