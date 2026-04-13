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
    ReviewItem,
    ReviewItemStatus,
    ReviewResultResponse,
    ReviewSettingsResponse,
    ReviewStage,
    ReviewStatus,
    ReviewTaskCreate,
    ReviewTaskResponse,
    RiskLevel,
)
from api.services.task_store import get_task, tasks
from config import get_default_retrieval_mode, get_default_web_search_enabled

router = APIRouter(prefix="/review", tags=["review"])
logger = logging.getLogger(__name__)


@router.get("/settings", response_model=ReviewSettingsResponse)
async def get_review_settings():
    return ReviewSettingsResponse(
        default_retrieval_mode=get_default_retrieval_mode(),
        default_web_search_enabled=get_default_web_search_enabled(),
    )


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
        "retrieval_mode": task.retrieval_mode,
        "web_search_enabled": task.web_search_enabled if task.web_search_enabled is not None else get_default_web_search_enabled(),
        "contract_name": contract_name,
        "result": None,
        "created_at": created_at,
        "completed_at": None,
        "error": None,
    }

    logger.info(
        "Review task %s created with retrieval_mode=%s",
        task_id,
        task.retrieval_mode.value if task.retrieval_mode else "default",
    )

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
        task_record = tasks[task_id]
        logger.info(
            "Review task %s starting with retrieval_mode=%s",
            task_id,
            task.retrieval_mode.value if task.retrieval_mode else "default",
        )
        result = await workflow.run(
            contract_path=task.contract_path,
            criteria_path=task.criteria_path,
            retrieval_mode=task.retrieval_mode.value if task.retrieval_mode else None,
            web_search_enabled=task_record.get("web_search_enabled"),
            progress_callback=progress_callback,
        )
        if result.get("retrieval_mode"):
            task_record["retrieval_mode"] = result["retrieval_mode"]
        if result.get("web_search_enabled") is not None:
            task_record["web_search_enabled"] = result["web_search_enabled"]

        issues = [
            IssueBase(
                section=issue.get("section"),
                criterion_id=issue.get("criterion_id"),
                criterion=issue.get("criterion"),
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
        review_items = [
            ReviewItem(
                criterion_id=item.get("criterion_id", ""),
                section=item.get("section", "其他"),
                criterion=item.get("criterion", ""),
                section_order=item.get("section_order", 0),
                criterion_order=item.get("criterion_order", 0),
                check_points=item.get("check_points", []),
                status=_coerce_review_item_status(item.get("status")),
                issue_count=item.get("issue_count", len(item.get("issues", []))),
                issues=[
                    IssueBase(
                        section=issue.get("section"),
                        criterion_id=issue.get("criterion_id"),
                        criterion=issue.get("criterion"),
                        clause_location=issue.get("clause_location", ""),
                        page=issue.get("page"),
                        risk_level=_coerce_risk_level(issue.get("risk_level")),
                        violated_criteria=issue.get("violated_criteria", ""),
                        conclusion=issue.get("conclusion", ""),
                        analysis=issue.get("analysis", ""),
                        legal_basis=issue.get("legal_basis"),
                        suggestion=issue.get("suggestion", ""),
                    )
                    for issue in item.get("issues", [])
                ],
                error_message=item.get("error_message"),
            )
            for item in result.get("review_items", [])
        ]

        completed_at = datetime.now()
        task_record["status"] = ReviewStatus.COMPLETED
        task_record["stage"] = ReviewStage.COMPLETED
        task_record["progress_message"] = "Review completed"
        task_record["completed_at"] = completed_at
        task_record["result"] = ReviewResultResponse(
            task_id=task_id,
            status=ReviewStatus.COMPLETED,
            contract_name=task_record.get("contract_name", ""),
            retrieval_mode=task_record.get("retrieval_mode"),
            web_search_enabled=task_record.get("web_search_enabled"),
            total_issues=len(issues),
            issues=issues,
            review_items=review_items,
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
        retrieval_mode=task.get("retrieval_mode"),
        web_search_enabled=task.get("web_search_enabled"),
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


def _coerce_review_item_status(raw_value: str | None) -> ReviewItemStatus:
    value = (raw_value or "").lower()
    if value == "compliant":
        return ReviewItemStatus.COMPLIANT
    if value == "error":
        return ReviewItemStatus.ERROR
    return ReviewItemStatus.ISSUES_FOUND
