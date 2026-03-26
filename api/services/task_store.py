from __future__ import annotations

from typing import Any


tasks: dict[str, dict[str, Any]] = {}


def get_task(task_id: str) -> dict[str, Any] | None:
    return tasks.get(task_id)


def list_tasks() -> list[dict[str, Any]]:
    return sorted(
        tasks.values(),
        key=lambda item: item.get("created_at"),
        reverse=True,
    )
