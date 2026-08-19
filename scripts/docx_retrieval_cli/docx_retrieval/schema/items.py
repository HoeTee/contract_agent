from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BodyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    anchor: str
    body_child_index: int
    text: str
    raw_text: str | None = None
    xml_path: str
    direct_outline: int | None = None
    style_outline: int | None = None
    style_id: str | None = None
    style_name: str | None = None
    num_id: str | None = None
    num_ilvl: int | None = None
    numbering_prefix: str | None = None
    alignment: str | None = None
    bold_fraction: float = 0.0
    max_font_size: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_breaks: int = 0

    @property
    def effective_outline(self) -> int | None:
        return self.direct_outline if self.direct_outline is not None else self.style_outline
