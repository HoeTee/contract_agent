from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, command: str, log_dir: Path | None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path: Path | None = None
        self._file = None
        if not enabled:
            return
        log_root = log_dir or Path("logs")
        log_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_command = command.replace("-", "_")
        self.path = log_root / f"{safe_command}_{timestamp}_{os.getpid()}.log"
        self._file = self.path.open("a", encoding="utf-8")
        self.write_line(f"started_at={datetime.now().isoformat(timespec='seconds')}")
        self.write_line(f"command={command}")

    def write_line(self, line: str = "") -> None:
        if not self._file:
            return
        self._file.write(line + "\n")
        self._file.flush()

    @property
    def stream(self):
        return self._file

    def write_json(self, label: str, value: Any) -> None:
        self.write_line(f"{label}:")
        self.write_line(json.dumps(_jsonable(value), ensure_ascii=False, indent=2))

    def log_args(self, args: Any) -> None:
        values = {}
        for key, value in vars(args).items():
            if key == "func" or key.startswith("_"):
                continue
            values[key] = _redact(key, _jsonable(value))
        self.write_json("args", values)

    def log_exception(self, exc: BaseException) -> None:
        self.write_line("error:")
        self.write_line("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())

    def close(self) -> None:
        if not self._file:
            return
        self.write_line(f"finished_at={datetime.now().isoformat(timespec='seconds')}")
        self._file.close()
        self._file = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _redact(key: str, value: Any) -> Any:
    lowered = key.lower()
    if "api_key" in lowered or "apikey" in lowered or lowered == "key":
        return "***REDACTED***" if value else value
    return value
