from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from docx_retrieval.llm.config import load_yaml


DEFAULT_RETRIEVAL_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


class VectorRetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    score_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    auto_build: bool = True


class RerankConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class ConcurrencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: int = Field(default=10, ge=1)
    embedding: int = Field(default=10, ge=1)
    reranker: int = Field(default=10, ge=1)


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=20000, ge=500)
    max_depth: int = Field(default=6, ge=1)
    vector: VectorRetrievalConfig = Field(default_factory=VectorRetrievalConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)

    @classmethod
    def from_sources(
        cls,
        config_path: Path | None = None,
        input_tokens: int | None = None,
        vector_enabled: bool | None = None,
        vector_score_threshold: float | None = None,
        vector_auto_build: bool | None = None,
        rerank_enabled: bool | None = None,
    ) -> "RetrievalConfig":
        raw = load_yaml(config_path or DEFAULT_RETRIEVAL_CONFIG)
        data: dict[str, Any] = dict(raw.get("retrieval") or {})
        vector = dict(data.get("vector") or {})
        rerank = dict(data.get("rerank") or {})
        concurrency = dict(raw.get("concurrency") or {})

        if input_tokens is not None:
            data["input_tokens"] = input_tokens
        if vector_enabled is not None:
            vector["enabled"] = vector_enabled
        if vector_score_threshold is not None:
            vector["score_threshold"] = vector_score_threshold
        if vector_auto_build is not None:
            vector["auto_build"] = vector_auto_build
        if rerank_enabled is not None:
            rerank["enabled"] = rerank_enabled

        data["vector"] = vector
        data["rerank"] = rerank
        data["concurrency"] = concurrency
        return cls.model_validate(data)
