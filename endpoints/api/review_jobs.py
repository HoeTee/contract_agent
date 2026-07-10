from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import DEFAULT_REVIEW_CRITERIA_PATH, MCP_SERVER_PATH
from endpoints.api.review import extract_api_meta_fields
from endpoints.api.task_store import (
    api_events_path,
    conversation_log_dir,
    create_task,
    ensure_task_dirs,
    input_dir,
    is_cancel_requested,
    mark_cancelled,
    mark_failed,
    mark_running,
    mark_succeeded,
    mcp_log_dir,
    new_task_id,
    output_dir,
    read_task,
    request_cancel,
    workflow_log_dir,
)
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.api_event_logger import append_api_event
from main_workflow.main_workflow import ContractReviewWorkflow
from endpoints.runtime.document_validation import validate_review_criteria_content, validate_uploaded_docx
from endpoints.runtime.errors import ModelCallError
from endpoints.runtime.filenames import build_report_display_name, safe_upload_filename
from endpoints.runtime.json_response import pretty_json_response
from endpoints.runtime.review_runtime import review_semaphore


api_jobs_router = APIRouter()


async def run_async_review_job(task_id: str) -> None:
    task = read_task(task_id)
    if task is None:
        return

    try:
        if is_cancel_requested(task_id):
            mark_cancelled(task_id)
            return

        mark_running(task_id)
        append_api_event(api_events_path(task_id), "review_started", task_id=task_id)

        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=str(workflow_log_dir(task_id)),
            conversation_log_dir=str(conversation_log_dir(task_id)),
            mcp_log_file=str(mcp_log_dir(task_id) / "mcp_client.log"),
            api_events_path=str(api_events_path(task_id)),
        )

        token = set_conversation_log_dir(conversation_log_dir(task_id))
        try:
            async def run_workflow():
                return await workflow.run(
                    contract_path=task["input"]["contract_path"],
                    criteria_path=task["input"]["criteria_path"],
                    output_path=task["output"]["result_path"],
                )

            if review_semaphore is None:
                result = await run_workflow()
            else:
                async with review_semaphore:
                    result = await run_workflow()
        finally:
            reset_conversation_log_dir(token)

        if is_cancel_requested(task_id):
            mark_cancelled(task_id)
            append_api_event(api_events_path(task_id), "review_cancelled", task_id=task_id)
            return

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise RuntimeError("Output DOCX file was not found.")

        mark_succeeded(task_id)
        append_api_event(api_events_path(task_id), "review_completed", result_file=str(output_path))
    except Exception as exc:
        if isinstance(exc, ModelCallError):
            append_api_event(
                api_events_path(task_id),
                exc.event_type,
                component=exc.component,
                error=str(exc),
            )
            mark_failed(task_id, code=exc.event_type, message=exc.user_message)
        else:
            mark_failed(task_id, code="REVIEW_FAILED", message="Review failed. Check task logs.")
        append_api_event(api_events_path(task_id), "review_failed", error=repr(exc))


@api_jobs_router.post("/api/review/jobs", status_code=202)
async def submit_review_job(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
    task_id = new_task_id()
    ensure_task_dirs(task_id)

    filename = safe_upload_filename(file.filename)
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Contract file must be DOCX.")

    meta_fields = await extract_api_meta_fields(request)
    contract_path = input_dir(task_id) / filename
    with contract_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    validate_uploaded_docx(contract_path)

    criteria_source = "default"
    criteria_filename = None
    selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)

    has_uploaded_criteria = bool(criteria_file and criteria_file.filename)
    if has_uploaded_criteria:
        criteria_filename = safe_upload_filename(criteria_file.filename)
        if not criteria_filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Review criteria file must be DOCX.")
        selected_criteria_path = input_dir(task_id) / criteria_filename
        with selected_criteria_path.open("wb") as f:
            shutil.copyfileobj(criteria_file.file, f)
        validate_uploaded_docx(selected_criteria_path)
        validate_review_criteria_content(selected_criteria_path)
        criteria_source = "uploaded"

    result_filename = build_report_display_name(filename)
    result_path = output_dir(task_id) / result_filename
    task = create_task(
        task_id=task_id,
        contract_filename=filename,
        contract_path=contract_path,
        criteria_source=criteria_source,
        criteria_filename=criteria_filename,
        criteria_path=selected_criteria_path,
        result_filename=result_filename,
        result_path=result_path,
        meta_fields=meta_fields,
    )
    append_api_event(
        api_events_path(task_id),
        "api_review_job_received",
        task_id=task_id,
        filename=filename,
        meta_fields=meta_fields,
    )
    background_tasks.add_task(run_async_review_job, task_id)
    return pretty_json_response(
        {
            "task_id": task["task_id"],
            "status": task["status"],
            "message": task["message"],
            "status_url": task["status_url"],
            "result_url": task["result_url"],
            "cancel_url": task["cancel_url"],
        },
        status_code=202,
    )


@api_jobs_router.get("/api/review/jobs/{task_id}")
async def get_review_job(task_id: str):
    try:
        task = read_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return pretty_json_response(task)


@api_jobs_router.get("/api/review/jobs/{task_id}/result")
async def download_review_job_result(task_id: str):
    try:
        task = read_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    status = task["status"]
    if status != "succeeded":
        raise HTTPException(status_code=409, detail=f"Task is not finished. Current status: {status}")

    result_path = Path(task["output"]["result_path"])
    if not result_path.exists():
        raise HTTPException(status_code=500, detail="Result file does not exist.")

    return FileResponse(
        path=result_path,
        filename=task["output"]["result_filename"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@api_jobs_router.post("/api/review/jobs/{task_id}/cancel")
async def cancel_review_job(task_id: str):
    try:
        task = read_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task["status"] in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Task is already finished and cannot be cancelled.")

    updated = request_cancel(task_id)
    return pretty_json_response(
        {
            "task_id": updated["task_id"],
            "status": updated["status"],
            "message": updated["message"],
        }
    )
