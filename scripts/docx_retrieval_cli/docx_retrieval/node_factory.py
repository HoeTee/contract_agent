from __future__ import annotations

from .constants import SUMMARY_TRIGGER_MIN_TOKENS
from .schema import BodyItem, Node
from .text import estimate_tokens, make_summary


def item_range_text(items: list[BodyItem], start: int, end: int) -> str:
    return "\n".join(item.text for item in items[start:end] if item.text).strip()


def item_page_range(items: list[BodyItem], start: int, end: int) -> tuple[int | None, int | None, str, int]:
    pages = [item.page_start for item in items[start:end] if item.page_start is not None]
    page_ends = [item.page_end for item in items[start:end] if item.page_end is not None]
    if not pages and not page_ends:
        return None, None, "unavailable", 0
    return min(pages), max(page_ends), "lastRenderedPageBreak", 1


def make_node(
    node_id: str,
    node_type: str,
    title: str,
    items: list[BodyItem],
    start: int,
    end: int,
    level: int | None,
    parent_id: str | None,
    score: int = 0,
    evidence: list[str] | None = None,
) -> Node:
    text = item_range_text(items, start, end)
    page_start, page_end, page_source, page_score = item_page_range(items, start, end)
    token_estimate = estimate_tokens(text)
    return Node(
        node_id=node_id,
        node_type=node_type,
        level=level,
        title=title or node_type,
        text=text,
        summary=make_summary(text) if token_estimate >= SUMMARY_TRIGGER_MIN_TOKENS else make_summary(title or text),
        start_anchor=items[start].anchor if start < len(items) else "",
        end_anchor=items[end - 1].anchor if end > start else (items[start].anchor if start < len(items) else ""),
        page_start=page_start,
        page_end=page_end,
        page_source=page_source,
        page_confidence_score=page_score,
        token_estimate=token_estimate,
        confidence_score=score,
        confidence_evidence=evidence or [],
        parent_id=parent_id,
        source_start=start,
        source_end=end,
    )
