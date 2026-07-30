from __future__ import annotations

import asyncio
from json import JSONDecodeError
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import (
    API_URL_DOWNLOAD_MAX_BYTES,
    API_URL_DOWNLOAD_TIMEOUT_SECONDS,
    DEFAULT_REVIEW_CRITERIA_PATH,
)
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
    save_task_input_url,
    save_task_input_upload,
    write_task_log_event,
)
from endpoints.runtime.document_validation import validate_review_criteria_content, validate_uploaded_docx
from endpoints.runtime.filenames import build_report_display_name, safe_upload_filename
from endpoints.runtime.json_response import pretty_json_response


api_jobs_router = APIRouter()


def _is_upload_file(value: object) -> bool:
    return hasattr(value, "filename") and hasattr(value, "file")


def _filename_from_url(file_url: str, fallback: str) -> str:
    raw_name = Path(urlsplit(file_url).path).name
    if not raw_name.lower().endswith(".docx"):
        return fallback
    return safe_upload_filename(raw_name)


def _url_for_log(file_url: str) -> str:
    parsed = urlsplit(file_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _download_http_status(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


@api_jobs_router.post("/api/review/jobs", status_code=202)
async def submit_review_job(request: Request):
    client = await resolve_api_client(request)
    task_id = new_task_id()
    ensure_task_dirs(client.client_dir, task_id)

    content_type = request.headers.get("content-type", "").lower()

    criteria_source = "default"
    criteria_filename = None
    selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        if "file_url" in form or "criteria_file_url" in form:
            raise HTTPException(status_code=400, detail="URL fields require application/json.")
        file = form.get("file")
        if not _is_upload_file(file) or not getattr(file, "filename", ""):
            raise HTTPException(status_code=400, detail="file is required.")

        filename = safe_upload_filename(file.filename)
        if not filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Contract file must be DOCX.")

        contract_path = save_task_input_upload(
            client.client_dir,
            task_id=task_id,
            upload_file=file,
            filename=filename,
        )
        write_task_log_event(
            client.client_dir,
            task_id,
            "contract_saved",
            file_path=str(contract_path),
            size_bytes=contract_path.stat().st_size,
        )
        validate_uploaded_docx(contract_path)

        criteria_file = form.get("criteria_file")
        if _is_upload_file(criteria_file) and getattr(criteria_file, "filename", ""):
            criteria_filename = safe_upload_filename(criteria_file.filename)
            if not criteria_filename.lower().endswith(".docx"):
                raise HTTPException(status_code=400, detail="Review criteria file must be DOCX.")
            selected_criteria_path = save_task_input_upload(
                client.client_dir,
                task_id=task_id,
                upload_file=criteria_file,
                filename=criteria_filename,
            )
            write_task_log_event(
                client.client_dir,
                task_id,
                "criteria_uploaded",
                file_path=str(selected_criteria_path),
                original_filename=criteria_filename,
                size_bytes=selected_criteria_path.stat().st_size,
            )
            validate_uploaded_docx(selected_criteria_path)
            validate_review_criteria_content(selected_criteria_path)
            criteria_source = "uploaded"
    elif content_type.startswith("application/json"):
        try:
            payload = await request.json()
        except JSONDecodeError:
            raise HTTPException(status_code=400, detail="JSON body must be valid.")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object.")

        file_url = payload.get("file_url")
        if not isinstance(file_url, str) or not file_url.strip():
            raise HTTPException(status_code=400, detail="file_url is required.")
        file_url = file_url.strip()
        filename = _filename_from_url(file_url, "contract_from_url.docx")
        try:
            contract_path = save_task_input_url(
                client.client_dir,
                task_id,
                file_url,
                filename,
                timeout_seconds=API_URL_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=API_URL_DOWNLOAD_MAX_BYTES,
            )
        except ValueError as exc:
            write_task_log_event(
                client.client_dir,
                task_id,
                "contract_url_download_failed",
                source_url=_url_for_log(file_url),
                http_status=None,
                error=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc))
        except httpx.HTTPError as exc:
            write_task_log_event(
                client.client_dir,
                task_id,
                "contract_url_download_failed",
                source_url=_url_for_log(file_url),
                http_status=_download_http_status(exc),
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail="Contract file URL download failed.")
        write_task_log_event(
            client.client_dir,
            task_id,
            "contract_url_downloaded",
            source_url=_url_for_log(file_url),
            file_path=str(contract_path),
            size_bytes=contract_path.stat().st_size,
        )
        validate_uploaded_docx(contract_path)

        criteria_file_url = payload.get("criteria_file_url")
        if criteria_file_url is not None:
            if not isinstance(criteria_file_url, str) or not criteria_file_url.strip():
                raise HTTPException(status_code=400, detail="criteria_file_url must be a non-empty string.")
            criteria_file_url = criteria_file_url.strip()
            criteria_filename = _filename_from_url(criteria_file_url, "criteria_from_url.docx")
            try:
                selected_criteria_path = save_task_input_url(
                    client.client_dir,
                    task_id,
                    criteria_file_url,
                    criteria_filename,
                    timeout_seconds=API_URL_DOWNLOAD_TIMEOUT_SECONDS,
                    max_bytes=API_URL_DOWNLOAD_MAX_BYTES,
                )
            except ValueError as exc:
                write_task_log_event(
                    client.client_dir,
                    task_id,
                    "criteria_url_download_failed",
                    source_url=_url_for_log(criteria_file_url),
                    http_status=None,
                    error=str(exc),
                )
                raise HTTPException(status_code=400, detail=str(exc))
            except httpx.HTTPError as exc:
                write_task_log_event(
                    client.client_dir,
                    task_id,
                    "criteria_url_download_failed",
                    source_url=_url_for_log(criteria_file_url),
                    http_status=_download_http_status(exc),
                    error=str(exc),
                )
                raise HTTPException(status_code=502, detail="Review criteria file URL download failed.")
            write_task_log_event(
                client.client_dir,
                task_id,
                "criteria_url_downloaded",
                source_url=_url_for_log(criteria_file_url),
                file_path=str(selected_criteria_path),
                size_bytes=selected_criteria_path.stat().st_size,
            )
            validate_uploaded_docx(selected_criteria_path)
            validate_review_criteria_content(selected_criteria_path)
            criteria_source = "uploaded"
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type.")

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
