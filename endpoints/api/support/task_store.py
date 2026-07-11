from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from config import API_KEEP_INPUT, API_WRITE_LOGS, DATA_DIR
from loggers.api_event_logger import append_api_event


TASK_ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{4}$")
BEIJING_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def new_task_id() -> str:
    created_at = datetime.now(BEIJING_TZ)
    return f"{created_at.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def validate_task_id(task_id: str) -> str:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError("invalid task_id")
    return task_id


def task_dir(task_id: str) -> Path:
    return Path(DATA_DIR) / "api" / validate_task_id(task_id)


def task_json_path(task_id: str) -> Path:
    return task_dir(task_id) / "task.json"


def input_dir(task_id: str) -> Path:
    return task_dir(task_id) / "input"


def output_dir(task_id: str) -> Path:
    return task_dir(task_id) / "output"


def logs_dir(task_id: str) -> Path:
    return task_dir(task_id) / "logs"


def workflow_log_dir(task_id: str) -> Path:
    return logs_dir(task_id) / "workflow"


def conversation_log_dir(task_id: str) -> Path:
    return logs_dir(task_id) / "conversations"


def mcp_log_dir(task_id: str) -> Path:
    return logs_dir(task_id) / "mcp"


def api_events_path(task_id: str) -> Path:
    return logs_dir(task_id) / "api_events.jsonl"


def runtime_input_dir(task_id: str) -> Path:
    return task_dir(task_id) / "runtime_input"


def should_write_task_file(kind: str) -> bool:
    if kind == "input":
        return bool(API_KEEP_INPUT)
    if kind == "output":
        return True
    if kind == "logs":
        return bool(API_WRITE_LOGS)
    raise ValueError(f"Unknown task file kind: {kind}")


def task_input_work_dir(task_id: str) -> Path:
    if should_write_task_file("input"):
        return input_dir(task_id)
    return runtime_input_dir(task_id)


def save_task_input_upload(task_id: str, upload_file: UploadFile, filename: str) -> Path:
    target_dir = task_input_work_dir(task_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    with target_path.open("wb") as f:
        shutil.copyfileobj(upload_file.file, f)
    return target_path


def save_task_input_copy(task_id: str, source_path: Path, filename: str) -> Path:
    target_dir = task_input_work_dir(task_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    shutil.copy2(source_path, target_path)
    return target_path


def cleanup_runtime_input(task_id: str) -> None:
    runtime_dir = runtime_input_dir(task_id)
    if not runtime_dir.exists():
        return
    shutil.rmtree(runtime_dir)


def task_api_events_path(task_id: str) -> Path | None:
    if not should_write_task_file("logs"):
        return None
    return api_events_path(task_id)


def task_workflow_log_dir(task_id: str) -> Path | None:
    if not should_write_task_file("logs"):
        return None
    return workflow_log_dir(task_id)


def task_conversation_log_dir(task_id: str) -> Path | None:
    if not should_write_task_file("logs"):
        return None
    return conversation_log_dir(task_id)


def task_mcp_log_file(task_id: str) -> Path | None:
    if not should_write_task_file("logs"):
        return None
    return mcp_log_dir(task_id) / "mcp_client.log"


def write_task_log_event(task_id: str, event: str, **fields: Any) -> Path | None:
    if not should_write_task_file("logs"):
        return None
    path = api_events_path(task_id)
    append_api_event(path, event, task_id=task_id, **fields)
    return path


def ensure_task_dirs(task_id: str) -> None:
    task_dir(task_id).mkdir(parents=True, exist_ok=True)
    output_dir(task_id).mkdir(parents=True, exist_ok=True)

    if should_write_task_file("input"):
        input_dir(task_id).mkdir(parents=True, exist_ok=True)

    if should_write_task_file("logs"):
        for path in (
            workflow_log_dir(task_id),
            conversation_log_dir(task_id),
            mcp_log_dir(task_id),
        ):
            path.mkdir(parents=True, exist_ok=True)


def write_task(task: dict[str, Any]) -> dict[str, Any]:
    path = task_json_path(task["task_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return task


def read_task(task_id: str) -> dict[str, Any] | None:
    path = task_json_path(task_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_task(task_id: str, **updates: Any) -> dict[str, Any]:
    task = read_task(task_id)
    if task is None:
        raise FileNotFoundError(task_id)
    task.update(updates)
    return write_task(task)


def create_task(
    *,
    task_id: str,
    contract_filename: str,
    contract_path: Path,
    criteria_source: str,
    criteria_filename: str | None,
    criteria_path: Path,
    result_filename: str,
    result_path: Path,
    meta_fields: dict[str, str],
) -> dict[str, Any]:
    task_api_log = task_api_events_path(task_id)
    task_workflow_log = task_workflow_log_dir(task_id)
    task_conversation_log = task_conversation_log_dir(task_id)
    task_mcp_log = task_mcp_log_file(task_id)
    task = {
        "task_id": task_id,
        "status": "queued",
        "status_url": f"/api/review/jobs/{task_id}",
        "result_url": f"/api/review/jobs/{task_id}/result",
        "cancel_url": f"/api/review/jobs/{task_id}/cancel",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "message": "Review job submitted.",
        "error": None,
        "input": {
            "contract_filename": contract_filename,
            "contract_path": str(contract_path),
            "criteria_source": criteria_source,
            "criteria_filename": criteria_filename,
            "criteria_path": str(criteria_path),
        },
        "output": {
            "result_filename": result_filename,
            "result_path": str(result_path),
        },
        "meta_fields": meta_fields,
        "cancel": {
            "requested": False,
            "requested_at": None,
            "cancelled_at": None,
        },
        "logs": {
            "api_events_path": str(task_api_log) if task_api_log else None,
            "workflow_log_dir": str(task_workflow_log) if task_workflow_log else None,
            "conversation_log_dir": str(task_conversation_log) if task_conversation_log else None,
            "mcp_log_file": str(task_mcp_log) if task_mcp_log else None,
        },
    }
    return write_task(task)


def mark_running(task_id: str) -> dict[str, Any]:
    return update_task(
        task_id,
        status="running",
        started_at=now_iso(),
        message="Contract review is running.",
    )


def mark_succeeded(task_id: str) -> dict[str, Any]:
    return update_task(
        task_id,
        status="succeeded",
        finished_at=now_iso(),
        message="Contract review succeeded.",
        error=None,
    )


def mark_failed(task_id: str, *, code: str, message: str) -> dict[str, Any]:
    return update_task(
        task_id,
        status="failed",
        finished_at=now_iso(),
        message="Contract review failed.",
        error={"code": code, "message": message},
    )


def request_cancel(task_id: str) -> dict[str, Any]:
    task = read_task(task_id)
    if task is None:
        raise FileNotFoundError(task_id)

    status = task["status"]
    if status == "queued":
        task["status"] = "cancelled"
        task["finished_at"] = now_iso()
        task["message"] = "Review job cancelled."
        task["cancel"]["requested"] = True
        task["cancel"]["requested_at"] = task["cancel"]["requested_at"] or now_iso()
        task["cancel"]["cancelled_at"] = now_iso()
        return write_task(task)

    return task


def is_cancel_requested(task_id: str) -> bool:
    task = read_task(task_id)
    if task is None:
        return False
    return bool(task.get("cancel", {}).get("requested"))


def mark_cancelled(task_id: str) -> dict[str, Any]:
    task = read_task(task_id)
    if task is None:
        raise FileNotFoundError(task_id)
    timestamp = now_iso()
    task["status"] = "cancelled"
    task["finished_at"] = timestamp
    task["message"] = "Review job cancelled."
    task["cancel"]["requested"] = True
    task["cancel"]["requested_at"] = task["cancel"]["requested_at"] or timestamp
    task["cancel"]["cancelled_at"] = timestamp
    return write_task(task)
