from __future__ import annotations

import re
from pathlib import Path

from config import DATA_DIR, USERS_FILE
from loggers.review_history import format_file_size, format_timestamp, load_history_records
from endpoints.runtime.auth import load_users, normalize_role


TASK_FILE_PREFIX_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}_")


def strip_task_file_prefix(filename: str | None) -> str:
    if not filename:
        return ""
    return TASK_FILE_PREFIX_RE.sub("", Path(filename.replace("\\", "/")).name)


def list_admin_users() -> list[dict]:
    rows = []
    data_dir = Path(DATA_DIR)
    for user in load_users(USERS_FILE):
        username = user.get("username", "")
        records = load_history_records(data_dir, username)
        latest_record = max(records, key=lambda item: item.get("report_created_at") or "", default={})
        rows.append({
            "username": username,
            "display_name": user.get("display_name") or username,
            "role": normalize_role(user.get("role")),
            "enabled": user.get("enabled", True),
            "history_count": len(records),
            "latest_review_at": latest_record.get("report_created_at") or "-",
        })
    return sorted(rows, key=lambda item: item["username"])


def get_admin_user(username: str) -> dict | None:
    for user in load_users(USERS_FILE):
        if user.get("username") == username:
            return {
                **user,
                "role": normalize_role(user.get("role")),
                "display_name": user.get("display_name") or username,
            }
    return None


def list_user_review_history(username: str) -> list[dict]:
    data_dir = Path(DATA_DIR)
    user_root = data_dir / username
    rows = []
    for record in load_history_records(data_dir, username):
        report_name = record.get("report_stored_name")
        report_exists = bool(report_name and (user_root / "reports_docx" / report_name).exists())
        rows.append({
            **record,
            "contract_display_name": record.get("contract_original_name") or strip_task_file_prefix(record.get("contract_stored_name")) or "-",
            "report_display_name": record.get("report_display_name") or strip_task_file_prefix(record.get("report_stored_name")) or "-",
            "contract_size": format_file_size(record.get("contract_size_bytes")),
            "report_size": format_file_size(record.get("report_size_bytes")),
            "report_exists": report_exists,
        })
    rows.sort(key=lambda item: item.get("report_created_at") or "", reverse=True)
    return rows


def get_user_criteria_info(username: str) -> dict:
    path = Path(DATA_DIR) / username / "contract_review_criteria" / "criteria.docx"
    if not path.exists():
        return {"exists": False, "size": "-", "updated_at": "-", "path": path}
    stat = path.stat()
    return {
        "exists": True,
        "size": format_file_size(stat.st_size),
        "updated_at": format_timestamp(stat.st_mtime),
        "path": path,
    }


def list_user_log_tasks(username: str) -> list[dict]:
    logs_root = Path(DATA_DIR) / username / "logs"
    if not logs_root.exists():
        return []

    rows = []
    for task_dir in logs_root.glob("*/*"):
        if not task_dir.is_dir():
            continue
        api_events = task_dir / "api_events.jsonl"
        stat = task_dir.stat()
        rows.append({
            "date": task_dir.parent.name,
            "task_name": task_dir.name,
            "relative_path": str(task_dir.relative_to(Path(DATA_DIR) / username)),
            "updated_at": format_timestamp(stat.st_mtime),
            "has_api_events": api_events.exists(),
        })
    rows.sort(key=lambda item: item["updated_at"], reverse=True)
    return rows


def admin_summary() -> dict:
    users = list_admin_users()
    return {
        "user_count": len(users),
        "admin_count": sum(1 for user in users if user["role"] == "admin"),
        "disabled_count": sum(1 for user in users if not user["enabled"]),
        "review_count": sum(user["history_count"] for user in users),
        "recent_reviews": sorted(
            [user for user in users if user["latest_review_at"] != "-"],
            key=lambda item: item["latest_review_at"],
            reverse=True,
        )[:10],
    }
