from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import DEFAULT_REVIEW_CRITERIA_PATH
from endpoints.api.client_mapping import resolve_api_client
from endpoints.review.job_worker import run_async_review_job
from endpoints.review.response import (
    present_review_task,
    present_submit_response,
)
from endpoints.review.task_store import (
    create_task,
    ensure_task_dirs,
    new_task_id,
    output_dir,
    read_task,
    request_cancel,
    save_task_input_upload,
    write_task_log_event,
)
from endpoints.runtime.document_validation import validate_review_criteria_content, validate_uploaded_docx
from endpoints.runtime.filenames import build_report_display_name, safe_upload_filename
from endpoints.runtime.json_response import pretty_json_response


api_jobs_router = APIRouter()


@api_jobs_router.post("/api/review/jobs", status_code=202)
async def submit_review_job(
    request: Request,
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
    client = await resolve_api_client(request)
    task_id = new_task_id()
    ensure_task_dirs(client.client_dir, task_id)

    filename = safe_upload_filename(file.filename)
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Contract file must be DOCX.")

    contract_path = save_task_input_upload(
        client.client_dir,
        task_id=task_id,
        upload_file=file,
        filename=filename,
    )
    validate_uploaded_docx(contract_path)

    criteria_source = "default"
    criteria_filename = None
    selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)

    has_uploaded_criteria = bool(criteria_file and criteria_file.filename)
    if has_uploaded_criteria:
        criteria_filename = safe_upload_filename(criteria_file.filename)
        if not criteria_filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Review criteria file must be DOCX.")
        selected_criteria_path = save_task_input_upload(
            client.client_dir,
            task_id=task_id,
            upload_file=criteria_file,
            filename=criteria_filename,
        )
        validate_uploaded_docx(selected_criteria_path)
        validate_review_criteria_content(selected_criteria_path)
        criteria_source = "uploaded"

    result_filename = build_report_display_name(filename)
    result_path = output_dir(client.client_dir, task_id) / result_filename
    task = create_task(
        client_id=client.client_id,
        client_dir=client.client_dir,
        task_id=task_id,
        contract_filename=filename,
        contract_path=contract_path,
        criteria_source=criteria_source,
        criteria_filename=criteria_filename,
        criteria_path=selected_criteria_path,
        result_filename=result_filename,
        result_path=result_path,
    )
    write_task_log_event(
        client.client_dir,
        task_id,
        "api_review_job_received",
        filename=filename,
        client_id=client.client_id,
        source_ip=client.source_ip,
    )
    asyncio.create_task(run_async_review_job(client.client_dir, task_id))
    return pretty_json_response(present_submit_response(task), status_code=202)


@api_jobs_router.get("/api/review/jobs/{task_id}")
async def get_review_job(request: Request, task_id: str):
    client = await resolve_api_client(request)
    try:
        task = read_task(client.client_dir, task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return pretty_json_response(present_review_task(task))


@api_jobs_router.post("/api/review/jobs/{task_id}/result")
async def export_review_job_result(
    request: Request,
    task_id: str,
):
    client = await resolve_api_client(request)
    try:
        task = read_task(client.client_dir, task_id)
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
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=result_path.name,
    )


@api_jobs_router.post("/api/review/jobs/{task_id}/cancel")
async def cancel_review_job(request: Request, task_id: str):
    client = await resolve_api_client(request)
    try:
        task = read_task(client.client_dir, task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task["status"] == "running":
        return pretty_json_response(
            {
                "task_id": task["task_id"],
                "status": task["status"],
                "message": "Review job has already started and cannot be cancelled.",
            },
            status_code=409,
        )

    if task["status"] in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Task is already finished and cannot be cancelled.")

    updated = request_cancel(client.client_dir, task_id)
    return pretty_json_response(
        {
            "task_id": updated["task_id"],
            "status": updated["status"],
            "message": updated["message"],
        }
    )
