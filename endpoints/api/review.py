from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import (
    API_CALLBACK_ENABLED,
    API_CALLBACK_FILE_FIELD,
    API_CALLBACK_URL,
    API_META_FIELDS,
    API_META_REQUIRED,
    DEFAULT_REVIEW_CRITERIA_PATH,
    MCP_SERVER_PATH,
)
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.api_event_logger import append_api_event
from main_workflow.main_workflow import ContractReviewWorkflow
from endpoints.api.callbacks import post_api_review_callback
from endpoints.api.task_store import (
    api_events_path,
    conversation_log_dir,
    create_task,
    ensure_task_dirs,
    input_dir,
    mark_failed,
    mark_running,
    mark_succeeded,
    mcp_log_dir,
    new_task_id,
    output_dir,
    workflow_log_dir,
)
from endpoints.runtime.document_validation import (
    DOCX_MEDIA_TYPE,
    validate_review_criteria_content,
    validate_uploaded_docx,
)
from endpoints.runtime.errors import ModelCallError
from endpoints.runtime.filenames import build_report_display_name, safe_upload_filename
from endpoints.runtime.json_response import pretty_json_response
from endpoints.runtime.review_runtime import review_semaphore


api_router = APIRouter()


def _header_name_for_meta_field(field_name: str) -> str:
    kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", field_name).replace("_", "-").lower()
    return f"x-{kebab}"


async def extract_api_meta_fields(request: Request) -> dict[str, str]:
    form = await request.form()
    meta_fields: dict[str, str] = {}
    missing: list[str] = []

    for field_name in API_META_FIELDS:
        raw_value = form.get(field_name)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        meta_fields[field_name] = value
        if API_META_REQUIRED and not value:
            missing.append(field_name)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"缺少必填字符串字段：{', '.join(missing)}",
        )

    return meta_fields


@api_router.post("/api/review")
async def api_review(
    request: Request,
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
    filename = safe_upload_filename(file.filename)
    task_id = new_task_id()
    task_api_events_path = api_events_path(task_id)
    task_created = False

    try:
        ensure_task_dirs(task_id)
        meta_fields = await extract_api_meta_fields(request)
        if API_CALLBACK_ENABLED and not API_CALLBACK_URL:
            raise HTTPException(
                status_code=500,
                detail="API_CALLBACK_ENABLED=True 时必须配置 API_CALLBACK_URL。",
            )
        append_api_event(
            task_api_events_path,
            "api_review_received",
            task_id=task_id,
            filename=filename,
            meta_fields=meta_fields,
        )

        if not filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=400,
                detail="系统支持的合同文件格式是 DOCX。",
            )

        selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)
        criteria_source = "default"
        criteria_filename = None

        has_uploaded_criteria = bool(criteria_file and criteria_file.filename)
        if has_uploaded_criteria:
            criteria_filename = safe_upload_filename(criteria_file.filename)
            if not criteria_filename.lower().endswith(".docx"):
                raise HTTPException(
                    status_code=400,
                    detail="审查要点文件格式必须是 DOCX。",
                )
            selected_criteria_path = input_dir(task_id) / criteria_filename
            with selected_criteria_path.open("wb") as f:
                shutil.copyfileobj(criteria_file.file, f)
            validate_uploaded_docx(selected_criteria_path)
            validate_review_criteria_content(selected_criteria_path)
            criteria_source = "uploaded"
            append_api_event(
                task_api_events_path,
                "criteria_uploaded",
                original_filename=criteria_filename,
                file_path=str(selected_criteria_path),
                size_bytes=selected_criteria_path.stat().st_size,
            )
        elif not selected_criteria_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"未找到系统默认审查要点文件：{selected_criteria_path}",
            )
        else:
            criteria_snapshot_path = input_dir(task_id) / selected_criteria_path.name
            shutil.copy2(selected_criteria_path, criteria_snapshot_path)
            selected_criteria_path = criteria_snapshot_path
            append_api_event(
                task_api_events_path,
                "criteria_default_saved",
                file_path=str(selected_criteria_path),
                size_bytes=selected_criteria_path.stat().st_size,
            )

        stored_contract_path = input_dir(task_id) / filename
        with stored_contract_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        append_api_event(
            task_api_events_path,
            "contract_saved",
            file_path=str(stored_contract_path),
            size_bytes=stored_contract_path.stat().st_size,
            criteria_source=criteria_source,
        )

        response_filename = build_report_display_name(filename)
        final_report_path = output_dir(task_id) / response_filename
        create_task(
            task_id=task_id,
            contract_filename=filename,
            contract_path=stored_contract_path,
            criteria_source=criteria_source,
            criteria_filename=criteria_filename,
            criteria_path=selected_criteria_path,
            result_filename=response_filename,
            result_path=final_report_path,
            meta_fields=meta_fields,
        )
        task_created = True

        validate_uploaded_docx(stored_contract_path)
        append_api_event(task_api_events_path, "docx_validation_passed")

        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=str(workflow_log_dir(task_id)),
            conversation_log_dir=str(conversation_log_dir(task_id)),
            mcp_log_file=str(mcp_log_dir(task_id) / "mcp_client.log"),
            api_events_path=str(task_api_events_path),
        )

        mark_running(task_id)
        append_api_event(task_api_events_path, "review_started", task_id=task_id)
        token = set_conversation_log_dir(conversation_log_dir(task_id))
        try:
            async def run_workflow():
                return await workflow.run(
                    contract_path=str(stored_contract_path),
                    criteria_path=str(selected_criteria_path),
                    output_path=str(final_report_path),
                )

            if review_semaphore is None:
                result = await run_workflow()
            else:
                async with review_semaphore:
                    result = await run_workflow()
        finally:
            reset_conversation_log_dir(token)

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise RuntimeError("未找到输出的 DOCX 文件。")

        mark_succeeded(task_id)
        append_api_event(task_api_events_path, "review_completed", result_file=str(output_path))
        await post_api_review_callback(
            output_path=output_path,
            response_filename=response_filename,
            meta_fields=meta_fields,
        )
        append_api_event(
            task_api_events_path,
            "api_callback_completed",
            enabled=API_CALLBACK_ENABLED,
            url=API_CALLBACK_URL if API_CALLBACK_ENABLED else "",
            file_field=API_CALLBACK_FILE_FIELD,
            meta_fields=meta_fields,
        )
        response_headers = {
            "x-review-task-id": task_id,
            "x-review-log-path": str(task_api_events_path),
            "x-review-criteria-source": criteria_source,
        }
        for field_name, field_value in meta_fields.items():
            response_headers[_header_name_for_meta_field(field_name)] = field_value
        return FileResponse(
            path=output_path,
            media_type=DOCX_MEDIA_TYPE,
            filename=response_filename,
            headers=response_headers,
        )

    except HTTPException as exc:
        append_api_event(
            task_api_events_path,
            "review_failed",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        if task_created:
            mark_failed(task_id, code="HTTP_ERROR", message=str(exc.detail))
        return pretty_json_response(
            {
                "task_id": task_id,
                "status": "failed",
                "message": exc.detail,
                "api_events_path": str(task_api_events_path),
            },
            status_code=exc.status_code,
        )
    except Exception as exc:
        status_code = 503 if isinstance(exc, ModelCallError) else 500
        if isinstance(exc, ModelCallError):
            message = f"审核失败：{exc.user_message}"
            append_api_event(
                task_api_events_path,
                exc.event_type,
                component=exc.component,
                error=str(exc),
            )
        else:
            message = "审核失败，请查看任务日志。"
        if task_created:
            mark_failed(
                task_id,
                code=exc.event_type if isinstance(exc, ModelCallError) else "REVIEW_FAILED",
                message=message,
            )
        append_api_event(task_api_events_path, "review_failed", error=repr(exc))
        return pretty_json_response(
            {
                "task_id": task_id,
                "status": "failed",
                "message": message,
                "api_events_path": str(task_api_events_path),
            },
            status_code=status_code,
        )
    finally:
        await file.close()
        if criteria_file:
            await criteria_file.close()
