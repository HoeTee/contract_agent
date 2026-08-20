from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from docx_retrieval.llm.config import load_yaml


DEFAULT_INDEXING_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


class TableIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inline_max_tokens: int = Field(default=10000, ge=500)
    chunk_target_tokens: int = Field(default=6000, ge=500)

    @model_validator(mode="after")
    def validate_chunk_budget(self) -> "TableIndexConfig":
        if self.chunk_target_tokens > self.inline_max_tokens:
            raise ValueError("indexing.table.chunk_target_tokens must not exceed inline_max_tokens")
        return self


class IndexingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: TableIndexConfig = Field(default_factory=TableIndexConfig)

    @classmethod
    def from_sources(cls, config_path: Path | None = None) -> "IndexingConfig":
        raw = load_yaml(config_path or DEFAULT_INDEXING_CONFIG)
        data: dict[str, Any] = dict(raw.get("indexing") or {})
        return cls.model_validate(data)
