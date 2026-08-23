from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from docxindex.detection.heading_profiles import (
    DEFAULT_PROFILE_EXAMPLES,
    CompiledHeadingProfile,
    compile_heading_profile,
)
from docxindex.llm.config import load_yaml


DEFAULT_INDEXING_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


class ParagraphIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split_threshold_tokens: int = Field(default=1000, ge=100)
    chunk_target_tokens: int = Field(default=700, ge=100)

    @model_validator(mode="after")
    def validate_chunk_budget(self) -> "ParagraphIndexConfig":
        if self.chunk_target_tokens > self.split_threshold_tokens:
            raise ValueError("indexing.paragraph.chunk_target_tokens must not exceed split_threshold_tokens")
        return self


class TableIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split_threshold_tokens: int = Field(default=20000, ge=500)
    chunk_target_tokens: int = Field(default=18000, ge=500)

    @model_validator(mode="after")
    def validate_chunk_budget(self) -> "TableIndexConfig":
        if self.chunk_target_tokens > self.split_threshold_tokens:
            raise ValueError("indexing.table.chunk_target_tokens must not exceed split_threshold_tokens")
        return self


class HeadingProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level_1_examples: list[str] = Field(min_length=1, max_length=5)
    level_2_examples: list[str] = Field(min_length=1, max_length=5)
    level_3_examples: list[str] = Field(min_length=1, max_length=5)


def _default_heading_profiles() -> dict[str, HeadingProfileConfig]:
    return {name: HeadingProfileConfig(**examples) for name, examples in DEFAULT_PROFILE_EXAMPLES.items()}


class HeadingIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, HeadingProfileConfig] = Field(default_factory=_default_heading_profiles, min_length=1)

    def compile_profiles(self) -> tuple[CompiledHeadingProfile, ...]:
        return tuple(
            compile_heading_profile(
                name,
                profile.level_1_examples,
                profile.level_2_examples,
                profile.level_3_examples,
            )
            for name, profile in self.profiles.items()
        )


class IndexingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph: ParagraphIndexConfig = Field(default_factory=ParagraphIndexConfig)
    table: TableIndexConfig = Field(default_factory=TableIndexConfig)
    heading: HeadingIndexConfig = Field(default_factory=HeadingIndexConfig)

    @classmethod
    def from_sources(cls, config_path: Path | None = None) -> "IndexingConfig":
        raw = load_yaml(config_path or DEFAULT_INDEXING_CONFIG)
        data: dict[str, Any] = dict(raw.get("indexing") or {})
        return cls.model_validate(data)
