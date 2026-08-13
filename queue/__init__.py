"""Queue integration for asynchronous review jobs.

This package intentionally uses the short name ``queue``. Re-export the
standard-library ``queue`` API so dependencies that run ``import queue`` keep
working even though this project package shadows the stdlib module on sys.path.
"""

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path

_stdlib_queue_path = Path(sysconfig.get_path("stdlib")) / "queue.py"
_stdlib_queue_spec = importlib.util.spec_from_file_location(
    "_stdlib_queue",
    _stdlib_queue_path,
)

if _stdlib_queue_spec is None or _stdlib_queue_spec.loader is None:
    raise ImportError(f"Unable to load standard-library queue from {_stdlib_queue_path}")

_stdlib_queue = importlib.util.module_from_spec(_stdlib_queue_spec)
_stdlib_queue_spec.loader.exec_module(_stdlib_queue)

for _name in getattr(_stdlib_queue, "__all__", ()):
    globals()[_name] = getattr(_stdlib_queue, _name)

__all__ = list(getattr(_stdlib_queue, "__all__", ()))
