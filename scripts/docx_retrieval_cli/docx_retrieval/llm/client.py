from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .config import env_api_key, find_project_config, load_yaml


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    base_url: str | None = None
    api_key: str = "EMPTY"
    temperature: float = 0.0
    timeout_seconds: float = 120.0
    enable_thinking: bool | None = None

    @classmethod
    def from_sources(
        cls,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        config_path: Path | None = None,
    ) -> "LLMSettings":
        config = load_yaml(config_path or find_project_config())
        llm = config.get("llm") or {}
        return cls(
            model=model or llm.get("name") or "qwen3.6-35b-a3b",
            base_url=base_url or llm.get("base_url"),
            api_key=api_key or env_api_key(),
            temperature=float(llm.get("temperature", 0.0)),
            enable_thinking=llm.get("enable_thinking"),
        )


class LLMClient:
    def __init__(self, settings: LLMSettings):
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def complete(self, prompt: str) -> str:
        extra_body = {}
        if self.settings.enable_thinking is not None:
            extra_body["enable_thinking"] = self.settings.enable_thinking
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.settings.temperature,
            extra_body=extra_body or None,
        )
        return response.choices[0].message.content or ""

    def complete_json(self, prompt: str) -> dict[str, Any]:
        return extract_json_object(self.complete(prompt))


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if "```" in text:
        text = re.sub(r"^.*?```(?:json)?\s*", "", text, flags=re.S)
        text = text.split("```", 1)[0]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"LLM response does not contain a JSON object: {content[:200]!r}")
    return json.loads(text[start : end + 1])
