"""Offline runtime defaults shared by all entry points."""
from __future__ import annotations

import os
from pathlib import Path


def configure_offline_tiktoken(project_root: str | os.PathLike[str] | None = None) -> None:
    """Point tiktoken at the project-bundled cache if no cache is configured."""
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parent
    cache_dir = root / "tiktoken_cache"
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(cache_dir))
