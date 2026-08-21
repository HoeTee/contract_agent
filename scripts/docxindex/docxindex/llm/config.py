from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def find_local_env(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    candidates = [
        current / ".env",
        current / "scripts" / "docxindex" / ".env",
    ]
    for directory in [current, *current.parents]:
        candidates.append(directory / "scripts" / "docxindex" / ".env")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_env_file(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    result = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


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
