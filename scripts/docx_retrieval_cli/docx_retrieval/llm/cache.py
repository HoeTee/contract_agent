from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


class JsonlCache:
    def __init__(self, path: Path | None):
        self.path = path
        self._data: dict[str, Any] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                self._data[record["key"]] = record["value"]

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
