from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BodyItem:
    kind: str
    anchor: str
    body_child_index: int
    text: str
    direct_outline: int | None = None
    style_outline: int | None = None
    style_id: str | None = None
    style_name: str | None = None
    alignment: str | None = None
    bold_fraction: float = 0.0
    max_font_size: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_breaks: int = 0

    @property
    def effective_outline(self) -> int | None:
        return self.direct_outline if self.direct_outline is not None else self.style_outline


@dataclass
class Node:
    node_id: str
    node_type: str
    title: str
    start_anchor: str
    end_anchor: str
    level: int | None = None
    parent_id: str | None = None
    text: str = ""
    summary: str = ""
    token_estimate: int = 0
    page_start: int | None = None
    page_end: int | None = None
    page_source: str = "unavailable"
    page_confidence_score: int = 0
    confidence_score: int = 0
    confidence_evidence: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None

    def to_storage(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "node_type": self.node_type,
            "level": self.level,
            "title": self.title,
            "text": self.text,
            "summary": self.summary,
            "start_anchor": self.start_anchor,
            "end_anchor": self.end_anchor,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "page_source": self.page_source,
            "page_confidence_score": self.page_confidence_score,
            "token_estimate": self.token_estimate,
            "confidence_score": self.confidence_score,
            "confidence_evidence": self.confidence_evidence,
            "children": [child.node_id for child in self.children],
        }

    def to_structure(self) -> dict[str, Any]:
        data = {
            "node_id": self.node_id,
            "title": self.title,
            "node_type": self.node_type,
            "summary": self.summary,
            "token_estimate": self.token_estimate,
        }
        if self.page_start is not None or self.page_end is not None:
            data["page_start"] = self.page_start
            data["page_end"] = self.page_end
        if self.children:
            data["children"] = [child.to_structure() for child in self.children]
        return data
