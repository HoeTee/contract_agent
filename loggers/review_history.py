from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


HISTORY_SCHEMA_VERSION = 2


def records_dir(data_dir: Path, username: str) -> Path:
    return data_dir / username / "records"


def history_file_path(data_dir: Path, username: str) -> Path:
    return records_dir(data_dir, username) / "review_history.json"


def tenant_task_root(data_dir: Path, tenant_id: str) -> Path:
    return data_dir / "web" / tenant_id


def task_json_path(data_dir: Path, tenant_id: str, task_id: str) -> Path:
    return tenant_task_root(data_dir, tenant_id) / task_id / "task.json"


def format_file_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "-"

    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def load_history_records(data_dir: Path, username: str, tenant_id: str = "") -> list[dict]:
    if tenant_id:
        root = tenant_task_root(data_dir, tenant_id)
        if not root.exists():
            return []
        records: list[dict] = []
        for task_json in sorted(root.glob("*/task.json")):
            try:
                record = json.loads(task_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get("username") == username:
                records.append(record)
        return records

    path = history_file_path(data_dir, username)
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_history_records(data_dir: Path, username: str, records: list[dict], tenant_id: str = "") -> None:
    if tenant_id:
        for record in records:
            task_id = record.get("task_id")
            if not task_id:
                continue
            save_task_record(data_dir, tenant_id, record)
        return

    path = history_file_path(data_dir, username)
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
        temp_path = Path(f.name)

    temp_path.replace(path)


def save_task_record(data_dir: Path, tenant_id: str, record: dict) -> None:
    path = task_json_path(data_dir, tenant_id, str(record["task_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
        temp_path = Path(f.name)
    temp_path.replace(path)


def append_history_record(data_dir: Path, username: str, record: dict, tenant_id: str = "") -> None:
    if tenant_id:
        save_task_record(data_dir, tenant_id, record)
        return

    records = load_history_records(data_dir, username)
    records = [item for item in records if item.get("task_id") != record.get("task_id")]
    records.append(record)
    save_history_records(data_dir, username, records)
