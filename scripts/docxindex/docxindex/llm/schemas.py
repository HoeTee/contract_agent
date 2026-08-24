from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)


class SummaryBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class SummaryBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summaries: list[SummaryBatchItem] = Field(default_factory=list)


class ExpandSubsection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(min_length=1)
    title: str = Field(min_length=1)
    level_hint: int | None = Field(default=None, ge=1, le=6)


class ExpandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subsections: list[ExpandSubsection] = Field(default_factory=list)


class AttachmentHeading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(min_length=1)
    title: str = Field(min_length=1)
    level: int = Field(ge=1, le=6)


class AttachmentLevelRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number_family: Literal[
        "subattachment",
        "chapter",
        "article",
        "section",
        "cn_comma",
        "cn_paren",
        "arabic_paren",
        "arabic_multilevel",
        "arabic_comma",
        "arabic_dot",
        "arabic_close",
        "letter",
    ]
    level: int = Field(ge=1, le=6)


class AttachmentHierarchySegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_anchor: str = Field(min_length=1)
    document_title: AttachmentHeading | None = None
    level_rules: list[AttachmentLevelRule] = Field(default_factory=list)
    additional_headings: list[AttachmentHeading] = Field(default_factory=list)


class AttachmentHierarchyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[AttachmentHierarchySegment] = Field(default_factory=list)


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


class RouteStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["title", "region", "rule", "join", "scan", "hybrid"]
    terms: list[str] = Field(default_factory=list)
    regions: list[Literal["frontmatter", "body", "tail", "attachments"]] = Field(default_factory=list)
    slots: list[str] = Field(default_factory=list)
    all_titles: bool = False
    context: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="before")
    @classmethod
    def flatten_params(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.pop("description", None)
        normalized.pop("reason", None)
        normalized.pop("condition", None)
        if "params" in normalized:
            params = normalized.pop("params")
            if not isinstance(params, dict):
                raise ValueError("route step params must be an object")
            if "check_keywords" in params and "terms" not in params:
                params["terms"] = params.pop("check_keywords")
            if "keywords" in params and "terms" not in params:
                params["terms"] = params.pop("keywords")
            target = params.pop("target", None)
            context_title = params.pop("context_title", None)
            if target:
                target_region = str(target).split("/", 1)[0]
                if target_region in {"frontmatter", "body", "tail", "attachments"}:
                    params.setdefault("regions", []).append(target_region)
                else:
                    params.setdefault("terms", []).append(str(target))
            if context_title:
                params.setdefault("terms", []).append(str(context_title))
            allowed = {"terms", "regions", "slots", "all_titles", "context"}
            for key, item in params.items():
                if key in allowed:
                    normalized.setdefault(key, item)
        if "check_keywords" in normalized and "terms" not in normalized:
            normalized["terms"] = normalized.pop("check_keywords")
        if "keywords" in normalized and "terms" not in normalized:
            normalized["terms"] = normalized.pop("keywords")
        target = normalized.pop("target", None)
        context_title = normalized.pop("context_title", None)
        if target:
            target_region = str(target).split("/", 1)[0]
            if target_region in {"frontmatter", "body", "tail", "attachments"}:
                normalized.setdefault("regions", []).append(target_region)
            else:
                normalized.setdefault("terms", []).append(str(target))
        if context_title:
            normalized.setdefault("terms", []).append(str(context_title))
        regions = normalized.get("regions")
        if isinstance(regions, list):
            normalized_regions = []
            for value in regions:
                region = str(value).split("/", 1)[0]
                if region in {"frontmatter", "body", "tail", "attachments"} and region not in normalized_regions:
                    normalized_regions.append(region)
            normalized["regions"] = normalized_regions
        executable = {"method", "terms", "regions", "slots", "all_titles", "context"}
        return {key: item for key, item in normalized.items() if key in executable}


class RouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[RouteStep] = Field(min_length=1, max_length=5)
    fallback: bool = False

    @model_validator(mode="before")
    @classmethod
    def keep_executable_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {key: item for key, item in value.items() if key in {"steps", "fallback"}}
