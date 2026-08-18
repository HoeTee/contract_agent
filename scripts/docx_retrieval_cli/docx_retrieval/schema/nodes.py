from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    parent_id: str | None = None
    node_type: str
    level: int | None = None
    title: str
    text: str = ""
    summary: str = ""
    start_anchor: str
    end_anchor: str
    page_start: int | None = None
    page_end: int | None = None
    page_source: str = "unavailable"
    page_confidence_score: int = 0
    token_estimate: int = 0
    confidence_score: int = 0
    confidence_evidence: list[str] = Field(default_factory=list)
    children: list["DocumentNode"] = Field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None

    def storage_view(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"children", "source_start", "source_end"})
        data["children"] = [child.node_id for child in self.children]
        return data

    def structure_view(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
            data["children"] = [child.structure_view() for child in self.children]
        return data

    def content_view(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "node_type": self.node_type,
            "text": self.text,
            "start_anchor": self.start_anchor,
            "end_anchor": self.end_anchor,
            "token_estimate": self.token_estimate,
        }
