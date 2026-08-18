from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from docx_retrieval.llm import LLMClient
from docx_retrieval.llm.cache import JsonlCache, cache_key, text_hash
from docx_retrieval.llm.prompts import EXPAND_PROMPT_VERSION, expand_prompt
from docx_retrieval.llm.schemas import ExpandResponse
from docx_retrieval.schema import BodyItem, DocumentNode

from .node_factory import make_node
from .splitter import split_long_leaf
from .token_budget import NODE_SOFT_LIMIT_TOKENS, estimate_tokens

EXPAND_BATCH_TARGET_TOKENS = 6000
EXPAND_BATCH_HARD_TOKENS = 10000
EXPAND_BATCH_OVERLAP_TOKENS = 800
ITEM_TEXT_MAX_CHARS = 1200
MAX_EXPAND_DEPTH = 4


@dataclass(frozen=True)
class ExpandCandidate:
    anchor: str
    title: str
    level_hint: int | None
    item_index: int


def expand_large_leaves(
    roots: list[DocumentNode],
    items: list[BodyItem],
    client: LLMClient,
    cache_dir: Path | None,
    concurrency: int = 10,
) -> None:
    cache = JsonlCache(cache_dir / "llm_expand.jsonl" if cache_dir else None)
    limiter = BoundedSemaphore(max(1, concurrency))
    for node in roots:
        _expand_node(node, items, client, cache, limiter, depth=0)


def _expand_node(
    node: DocumentNode,
    items: list[BodyItem],
    client: LLMClient,
    cache: JsonlCache,
    limiter: BoundedSemaphore,
    depth: int,
) -> None:
    for child in node.children:
        _expand_node(child, items, client, cache, limiter, depth)
    if node.children:
        return
    if depth >= MAX_EXPAND_DEPTH:
        _fallback_chunk(node, items)
        return
    if node.source_start is None or node.source_end is None:
        return
    if node.token_estimate <= NODE_SOFT_LIMIT_TOKENS:
        return

    candidates = _collect_candidates(node, items, client, cache, limiter)
    children = _build_semantic_children(node, items, candidates)
    if children:
        node.children = children
        for child in node.children:
            _expand_node(child, items, client, cache, limiter, depth + 1)
    else:
        _fallback_chunk(node, items)


def _fallback_chunk(node: DocumentNode, items: list[BodyItem]) -> None:
    if node.source_start is None or node.source_end is None:
        return
    split_long_leaf(node, items, node.source_start, node.source_end)


def _collect_candidates(
    node: DocumentNode,
    items: list[BodyItem],
    client: LLMClient,
    cache: JsonlCache,
    limiter: BoundedSemaphore,
) -> list[ExpandCandidate]:
    if node.source_start is None or node.source_end is None:
        return []
    windows = _make_windows(items, node.source_start, node.source_end)
    raw_candidates: list[dict[str, Any]] = []
    for start, end in windows:
        payload = _format_items(items, start, end)
        key = cache_key(
            EXPAND_PROMPT_VERSION,
            client.settings.model,
            node.node_id,
            items[start].anchor,
            items[end - 1].anchor,
            text_hash(payload),
        )
        cached = cache.get(key)
        if cached is None:
            with limiter:
                response = client.complete_model(
                    expand_prompt(node.node_id, node.title, items[start].anchor, items[end - 1].anchor, payload),
                    ExpandResponse,
                )
            cached = response.model_dump(mode="json")
            cache.set(key, cached)
        raw_candidates.extend(cached.get("subsections") or [])
    return _validate_candidates(node, items, raw_candidates)


def _make_windows(items: list[BodyItem], start: int, end: int) -> list[tuple[int, int]]:
    windows = []
    index = start
    while index < end:
        current = index
        tokens = 0
        while current < end:
            item_tokens = estimate_tokens(_format_item(items[current]))
            if current > index and tokens + item_tokens > EXPAND_BATCH_HARD_TOKENS:
                break
            tokens += item_tokens
            current += 1
            if tokens >= EXPAND_BATCH_TARGET_TOKENS:
                break
        if current <= index:
            current = index + 1
        windows.append((index, current))
        if current >= end:
            break
        overlap_tokens = 0
        overlap_start = current
        while overlap_start > index and overlap_tokens < EXPAND_BATCH_OVERLAP_TOKENS:
            overlap_start -= 1
            overlap_tokens += estimate_tokens(_format_item(items[overlap_start]))
        index = overlap_start if overlap_start > index else current
    return windows


def _format_items(items: list[BodyItem], start: int, end: int) -> str:
    return "\n".join(_format_item(item) for item in items[start:end] if item.text)


def _format_item(item: BodyItem) -> str:
    text = item.text
    if len(text) > ITEM_TEXT_MAX_CHARS:
        text = text[:ITEM_TEXT_MAX_CHARS].rstrip() + "..."
    return f"[{item.anchor}] ({item.kind}, body_child_index={item.body_child_index}) {text}"


def _validate_candidates(node: DocumentNode, items: list[BodyItem], raw_candidates: list[dict[str, Any]]) -> list[ExpandCandidate]:
    if node.source_start is None or node.source_end is None:
        return []
    by_anchor = {item.anchor: index for index, item in enumerate(items[node.source_start : node.source_end], start=node.source_start)}
    result_by_anchor: dict[str, ExpandCandidate] = {}
    for raw in raw_candidates:
        anchor = str(raw.get("anchor") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not anchor or not title or anchor not in by_anchor:
            continue
        index = by_anchor[anchor]
        item_text = items[index].text.strip()
        if not item_text or not (item_text == title or item_text.startswith(title) or title.startswith(item_text[: min(len(item_text), len(title))])):
            continue
        if anchor == node.start_anchor and (title == node.title or node.title.startswith(title) or title.startswith(node.title)):
            continue
        level_hint = _clean_level_hint(raw.get("level_hint"))
        current = result_by_anchor.get(anchor)
        candidate = ExpandCandidate(anchor=anchor, title=title, level_hint=level_hint, item_index=index)
        if current is None or len(candidate.title) > len(current.title):
            result_by_anchor[anchor] = candidate
    candidates = sorted(result_by_anchor.values(), key=lambda item: item.item_index)
    if len(candidates) < 2:
        return []
    return candidates


def _clean_level_hint(value: Any) -> int | None:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return level if 1 <= level <= 6 else None


def _build_semantic_children(node: DocumentNode, items: list[BodyItem], candidates: list[ExpandCandidate]) -> list[DocumentNode]:
    if not candidates or node.source_start is None or node.source_end is None:
        return []
    normalized = [(candidate.item_index, candidate.level_hint or 1, candidate.title) for candidate in candidates]
    if len(normalized) < 2:
        return []

    roots: list[DocumentNode] = []
    stack: list[tuple[int, DocumentNode]] = []
    sibling_counts: dict[tuple[str, int], int] = {}
    for pos, (index, level, title) in enumerate(normalized):
        next_index = node.source_end
        for future_index, future_level, _ in normalized[pos + 1 :]:
            if future_level <= level:
                next_index = future_index
                break
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1].node_id if stack else node.node_id
        key = (parent_id, level)
        sibling_counts[key] = sibling_counts.get(key, 0) + 1
        child_id = f"{parent_id}/llm_{sibling_counts[key]:03d}" if not stack else f"{parent_id}/l{level}_{sibling_counts[key]:03d}"
        child = make_node(
            child_id,
            "semantic_section",
            title,
            items,
            index,
            next_index,
            level,
            parent_id,
            score=1,
            evidence=["llm_expand"],
        )
        if stack:
            stack[-1][1].children.append(child)
        else:
            roots.append(child)
        stack.append((level, child))
    return roots
