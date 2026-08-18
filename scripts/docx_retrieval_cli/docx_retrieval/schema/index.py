from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnchorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_child_index: int
    type: str
    text: str
    node_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    xml_path: str


class DocumentIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "docx-index-v2"
    source_file: str
    top_regions: dict[str, str]
    settings: dict[str, Any]
    nodes: list[dict[str, Any]]
    root_nodes: list[str]
    structure_tree: list[dict[str, Any]]
    anchor_map: dict[str, AnchorRecord]

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
