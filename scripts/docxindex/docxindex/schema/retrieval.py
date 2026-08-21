from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RetrievalMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str
    match_type: str
    match_text: str
    node_id: str
    anchor: str | None = None


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matches: list[RetrievalMatch]
