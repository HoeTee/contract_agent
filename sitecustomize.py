"""Process-wide startup defaults for offline deployments.

Python imports this module automatically when the project root is on sys.path.
Set the tiktoken cache before application modules import tiktoken directly.
"""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
TIKTOKEN_CACHE_DIR = PROJECT_ROOT / "tiktoken_cache"

os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(TIKTOKEN_CACHE_DIR))
