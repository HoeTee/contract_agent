from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock, RLock
from typing import Any


_PATH_LOCKS: dict[str, RLock] = {}
_PATH_LOCKS_GUARD = Lock()


def _path_lock(path: Path | None) -> RLock:
    key = str(path.resolve()) if path else "<memory>"
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, RLock())


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


class JsonlCache:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = _path_lock(path)
        self._data: dict[str, Any] = {}
        with self._lock:
            if path and path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    self._data[record["key"]] = record["value"]

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            if not self.path:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
