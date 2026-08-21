from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from docxindex.llm.config import find_local_env, find_project_config, load_env_file, load_yaml
from docxindex.llm.client import os_env

EMBEDDING_BATCH_SIZE = 10


class EmbeddingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    base_url: str | None = None
    api_key: str = "EMPTY"
    timeout_seconds: float = 120.0

    @classmethod
    def from_sources(
        cls,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        config_path: Path | None = None,
    ) -> "EmbeddingSettings":
        local_env = load_env_file(find_local_env())
        config = load_yaml(config_path or find_project_config())
        embedding = config.get("embedding") or {}
        return cls(
            model=(
                model
                or local_env.get("EMBEDDING_MODEL_NAME")
                or os_env("EMBEDDING_MODEL_NAME")
                or embedding.get("name")
                or "text-embedding-v4"
            ),
            base_url=base_url or local_env.get("EMBEDDING_BASE") or os_env("EMBEDDING_BASE") or embedding.get("base_url"),
            api_key=api_key or local_env.get("EMBED_API_KEY") or os_env("EMBED_API_KEY") or "EMPTY",
        )


class EmbeddingClient:
    def __init__(self, settings: EmbeddingSettings):
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + EMBEDDING_BATCH_SIZE]
            response = self.client.embeddings.create(model=self.settings.model, input=batch)
            result.extend(list(item.embedding) for item in response.data)
        return result
