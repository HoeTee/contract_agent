from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import DATA_DIR


TASK_ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{4}$")
BEIJING_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat(timespec="seconds")


def new_task_id() -> str:
    created_at = datetime.now(BEIJING_TZ)
    return f"{created_at.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def validate_task_id(task_id: str) -> str:
    if not TASK_ID_PATTERN.match(task_id):
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


def ensure_task_dirs(task_id: str) -> None:
    for path in (
        task_dir(task_id),
        input_dir(task_id),
        output_dir(task_id),
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
            "api_events_path": str(api_events_path(task_id)),
            "workflow_log_dir": str(workflow_log_dir(task_id)),
            "conversation_log_dir": str(conversation_log_dir(task_id)),
            "mcp_log_dir": str(mcp_log_dir(task_id)),
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

    if status == "running":
        task["status"] = "cancelling"
        task["message"] = "Review job cancellation requested."
        task["cancel"]["requested"] = True
        task["cancel"]["requested_at"] = task["cancel"]["requested_at"] or now_iso()
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
