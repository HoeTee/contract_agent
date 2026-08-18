from __future__ import annotations

from pathlib import Path

from docx_retrieval.llm import LLMClient
from docx_retrieval.llm.cache import JsonlCache, cache_key, text_hash
from docx_retrieval.llm.prompts import SUMMARY_PROMPT_VERSION, summary_prompt
from docx_retrieval.llm.schemas import SummaryResponse
from docx_retrieval.schema import DocumentNode

from .token_budget import SUMMARY_TRIGGER_MIN_TOKENS, estimate_tokens

SUMMARY_INPUT_TARGET_TOKENS = 6000
SUMMARY_OUTPUT_MAX_TOKENS = 200


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
        cached = _generate_summary(client, node, content)
        cached["summary"] = cached["summary"].strip()
        cache.set(key, cached)
    if cached.get("summary"):
        node.summary = cached["summary"]
    return node.summary


def _generate_summary(client: LLMClient, node: DocumentNode, content: str) -> dict[str, str]:
    prompt = summary_prompt(node.title, node.node_type, content, max_tokens=SUMMARY_OUTPUT_MAX_TOKENS)
    last_summary = ""
    for attempt in range(3):
        response = client.complete_model(prompt, SummaryResponse)
        summary = response.summary.strip()
        last_summary = summary
        if estimate_tokens(summary) <= SUMMARY_OUTPUT_MAX_TOKENS:
            return {"summary": summary}
        prompt = (
            f"{prompt}\n\n"
            f"上一版摘要超过 {SUMMARY_OUTPUT_MAX_TOKENS} tokens，必须压缩。"
            "只保留合同审查导航必需信息，返回同样 JSON schema。"
        )
    return {"summary": _truncate_summary(last_summary)}


def _truncate_summary(summary: str) -> str:
    if estimate_tokens(summary) <= SUMMARY_OUTPUT_MAX_TOKENS:
        return summary
    chars = max(120, int(len(summary) * SUMMARY_OUTPUT_MAX_TOKENS / max(estimate_tokens(summary), 1)))
    return summary[:chars].rstrip()


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
