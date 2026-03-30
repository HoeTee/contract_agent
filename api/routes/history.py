from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from api.models.schemas import HistoryItem
from api.services.task_store import get_task, list_tasks

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=List[HistoryItem])
async def get_history():
    items = []
    for task in list_tasks():
        result = task.get("result")
        items.append(
            HistoryItem(
                task_id=task["task_id"],
                contract_name=task.get("contract_name") or task["task_id"],
                status=task["status"],
                created_at=task["created_at"],
                completed_at=task.get("completed_at"),
                retrieval_mode=task.get("retrieval_mode"),
                stage=task.get("stage"),
                progress_message=task.get("progress_message"),
                total_issues=result.total_issues if result else 0,
                error=task.get("error"),
            )
        )
    return items


@router.get("/{task_id}", response_model=HistoryItem)
async def get_history_detail(task_id: str):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = task.get("result")
    return HistoryItem(
        task_id=task["task_id"],
        contract_name=task.get("contract_name") or task["task_id"],
        status=task["status"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        retrieval_mode=task.get("retrieval_mode"),
        stage=task.get("stage"),
        progress_message=task.get("progress_message"),
        total_issues=result.total_issues if result else 0,
        error=task.get("error"),
    )
