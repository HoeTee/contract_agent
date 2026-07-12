from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile

from config import DEFAULT_REVIEW_CRITERIA_PATH
from endpoints.review.job_worker import run_async_review_job
from endpoints.review.meta import extract_api_meta_fields
from endpoints.review.response import (
    present_export_response,
    present_review_task,
    present_submit_response,
)
from endpoints.review.task_store import (
    create_task,
    ensure_task_dirs,
    export_task_result,
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
    contract_path = save_task_input_upload(
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
            task_id=task_id,
            upload_file=criteria_file,
            filename=criteria_filename,
        )
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
    write_task_log_event(
        task_id,
        "api_review_job_received",
        filename=filename,
        meta_fields=meta_fields,
    )
    background_tasks.add_task(run_async_review_job, task_id)
    return pretty_json_response(present_submit_response(task), status_code=202)


@api_jobs_router.get("/api/review/jobs/{task_id}")
async def get_review_job(task_id: str):
    try:
        task = read_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return pretty_json_response(present_review_task(task))


@api_jobs_router.post("/api/review/jobs/{task_id}/result")
async def export_review_job_result(
    task_id: str,
    payload: dict | None = Body(None),
):
    try:
        task = read_task(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    status = task["status"]
    if status != "succeeded":
        raise HTTPException(status_code=409, detail=f"Task is not finished. Current status: {status}")

    output_path = payload.get("output_path") if isinstance(payload, dict) else None
    if not isinstance(output_path, str) or not output_path.strip():
        return pretty_json_response(
            {
                "task_id": task_id,
                "status": "failed",
                "message": "output_path is required.",
            },
            status_code=400,
        )

    try:
        exported_path = export_task_result(task, output_path)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Result file does not exist.")
    except OSError as exc:
        return pretty_json_response(
            {
                "task_id": task_id,
                "status": "failed",
                "message": f"Failed to export result: {exc}",
                "output_path": output_path,
            },
            status_code=500,
        )

    return pretty_json_response(
        present_export_response(task, exported_path)
    )


@api_jobs_router.post("/api/review/jobs/{task_id}/cancel")
async def cancel_review_job(task_id: str):
    try:
        task = read_task(task_id)
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

    updated = request_cancel(task_id)
    return pretty_json_response(
        {
            "task_id": updated["task_id"],
            "status": updated["status"],
            "message": updated["message"],
        }
    )
