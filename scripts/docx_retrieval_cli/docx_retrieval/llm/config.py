from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def find_project_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / "config.yaml"
        if candidate.exists():
            return candidate
    return None


def load_yaml(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def env_api_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("CHATGPT_API_KEY")
        or os.getenv("LLM_API_KEY")
        or "EMPTY"
    )
