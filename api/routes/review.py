from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from api.dependencies.workflow import get_workflow
from api.models.schemas import (
    IssueBase,
    ReviewResultResponse,
    ReviewStage,
    ReviewStatus,
    ReviewTaskCreate,
    ReviewTaskResponse,
    RiskLevel,
)
from api.services.task_store import get_task, tasks

router = APIRouter(prefix="/review", tags=["review"])
logger = logging.getLogger(__name__)


@router.post("/start", response_model=ReviewTaskResponse)
async def start_review(
    task: ReviewTaskCreate,
    background_tasks: BackgroundTasks,
    workflow=Depends(get_workflow),
):
    task_id = str(uuid.uuid4())
    contract_name = task.contract_path.split("/")[-1].split("\\")[-1]
    created_at = datetime.now()

    tasks[task_id] = {
        "task_id": task_id,
        "status": ReviewStatus.PROCESSING,
        "stage": ReviewStage.QUEUED,
        "progress_message": "Task created",
        "contract_path": task.contract_path,
        "criteria_path": task.criteria_path,
        "contract_name": contract_name,
        "result": None,
        "created_at": created_at,
        "completed_at": None,
        "error": None,
    }

    background_tasks.add_task(run_review_task, task_id, task, workflow)
    return _build_task_response(tasks[task_id])


async def run_review_task(task_id: str, task: ReviewTaskCreate, workflow):
    async def progress_callback(update: dict):
        task_record = get_task(task_id)
        if task_record is None:
            return

        stage_value = update.get("stage")
        if stage_value:
            task_record["stage"] = ReviewStage(stage_value)
        task_record["progress_message"] = update.get("message")

    try:
        result = await workflow.run(
            contract_path=task.contract_path,
            criteria_path=task.criteria_path,
            progress_callback=progress_callback,
        )

        issues = [
            IssueBase(
                clause_location=issue.get("clause_location", ""),
                page=issue.get("page"),
                risk_level=_coerce_risk_level(issue.get("risk_level")),
                violated_criteria=issue.get("violated_criteria", ""),
                conclusion=issue.get("conclusion", ""),
                analysis=issue.get("analysis", ""),
                legal_basis=issue.get("legal_basis"),
                suggestion=issue.get("suggestion", ""),
            )
            for issue in result.get("issues", [])
        ]

        completed_at = datetime.now()
        task_record = tasks[task_id]
        task_record["status"] = ReviewStatus.COMPLETED
        task_record["stage"] = ReviewStage.COMPLETED
        task_record["progress_message"] = "Review completed"
        task_record["completed_at"] = completed_at
        task_record["result"] = ReviewResultResponse(
            task_id=task_id,
            status=ReviewStatus.COMPLETED,
            contract_name=task_record.get("contract_name", ""),
            total_issues=len(issues),
            issues=issues,
            report_md=result.get("report_md"),
            report_docx=result.get("report_docx"),
            report_pdf=result.get("report_pdf"),
            completed_at=completed_at,
            stage=ReviewStage.COMPLETED,
            progress_message="Review completed",
        )
    except Exception as exc:
        logger.exception("Review task %s failed", task_id)
        task_record = tasks[task_id]
        task_record["status"] = ReviewStatus.FAILED
        task_record["stage"] = ReviewStage.FAILED
        task_record["progress_message"] = "Review failed"
        task_record["error"] = str(exc)
        task_record["completed_at"] = datetime.now()


@router.get("/{task_id}", response_model=ReviewTaskResponse)
async def get_review_status(task_id: str):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _build_task_response(task)


@router.get("/{task_id}/result", response_model=ReviewResultResponse)
async def get_review_result(task_id: str):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != ReviewStatus.COMPLETED or task.get("result") is None:
        raise HTTPException(status_code=400, detail="Task not completed")
    return task["result"]


@router.get("/{task_id}/artifact/{artifact_type}")
async def download_review_artifact(task_id: str, artifact_type: str):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != ReviewStatus.COMPLETED or task.get("result") is None:
        raise HTTPException(status_code=400, detail="Task not completed")
    if artifact_type not in {"md", "docx", "pdf"}:
        raise HTTPException(status_code=404, detail="Unknown artifact type")

    result: ReviewResultResponse = task["result"]
    artifact_path = getattr(result, f"report_{artifact_type}")
    if not artifact_path or not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    media_types = {
        "md": "text/markdown; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    return FileResponse(
        artifact_path,
        media_type=media_types[artifact_type],
        filename=os.path.basename(artifact_path),
    )


def _build_task_response(task: dict) -> ReviewTaskResponse:
    return ReviewTaskResponse(
        task_id=task["task_id"],
        status=task["status"],
        created_at=task.get("created_at", datetime.now()),
        contract_name=task.get("contract_name"),
        stage=task.get("stage"),
        progress_message=task.get("progress_message"),
        error=task.get("error"),
    )


def _coerce_risk_level(raw_value: str | None) -> RiskLevel:
    value = (raw_value or "").lower()
    if "high" in value or "高" in (raw_value or ""):
        return RiskLevel.HIGH
    if "medium" in value or "中" in (raw_value or ""):
        return RiskLevel.MEDIUM
    if "none" in value or "无" in (raw_value or ""):
        return RiskLevel.NONE
    return RiskLevel.LOW
