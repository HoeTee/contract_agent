from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class IndexingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph: ParagraphIndexConfig = Field(default_factory=ParagraphIndexConfig)
    table: TableIndexConfig = Field(default_factory=TableIndexConfig)

    @classmethod
    def from_sources(cls, config_path: Path | None = None) -> "IndexingConfig":
        raw = load_yaml(config_path or DEFAULT_INDEXING_CONFIG)
        data: dict[str, Any] = dict(raw.get("indexing") or {})
        return cls.model_validate(data)
