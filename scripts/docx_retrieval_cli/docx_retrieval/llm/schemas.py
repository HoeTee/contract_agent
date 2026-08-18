from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)


class ExpandSubsection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(min_length=1)
    title: str = Field(min_length=1)
    level_hint: int | None = Field(default=None, ge=1, le=6)


class ExpandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subsections: list[ExpandSubsection] = Field(default_factory=list)


class QueryMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    reason: str = ""


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[QueryMatch] = Field(default_factory=list)


class RerankMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class RerankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[RerankMatch] = Field(default_factory=list)
