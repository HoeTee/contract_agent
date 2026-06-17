from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from config import (
    API_CALLBACK_ENABLED,
    API_CALLBACK_FILE_FIELD,
    API_CALLBACK_URL,
    API_META_FIELDS,
    API_META_REQUIRED,
    API_STORE,
    DATA_DIR,
    DEFAULT_REVIEW_CRITERIA_PATH,
    MCP_SERVER_PATH,
)
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.api_event_logger import append_api_event
from loggers.resolve_api_review_paths import resolve_api_review_paths
from main_workflow.main_workflow import ContractReviewWorkflow
from web.api.callbacks import post_api_review_callback
from web.core.document_validation import (
    DOCX_MEDIA_TYPE,
    validate_review_criteria_content,
    validate_uploaded_docx,
)
from web.core.errors import ModelCallError
from web.core.filenames import build_report_display_name, safe_upload_filename
from web.core.review_runtime import review_semaphore


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
    file: UploadFile = File(...), # 合同文件必须上传，否则返回 422 错误；定义了 multipart
    criteria_file: UploadFile | None = File(None),
):
    filename = safe_upload_filename(file.filename)
    paths = resolve_api_review_paths(
        original_filename=filename,
        data_dir=Path(DATA_DIR),
        store_enabled=API_STORE,
    )

    try:
        paths.ensure_dirs() # 创建本地 API 任务持久目录
        meta_fields = await extract_api_meta_fields(request)
        if API_CALLBACK_ENABLED and not API_CALLBACK_URL:
            raise HTTPException(
                status_code=500,
                detail="API_CALLBACK_ENABLED=True 时必须配置 API_CALLBACK_URL。",
            )
        append_api_event( 
            paths.api_events_path,
            "api_review_received",
            task_id=paths.task_id,
            filename=filename,
            meta_fields=meta_fields,
        ) # 写一条 API 日志，记录收到 API 请求和上传文件的基本信息

        if not filename.lower().endswith(".docx"): # 如果不是 .docx 结尾
            raise HTTPException(
                status_code=400,
                detail="系统支持的合同文件格式是 DOCX。",
            )

        selected_criteria_path = Path(DEFAULT_REVIEW_CRITERIA_PATH) # 系统默认审查要点来源
        criteria_source = "default"
        criteria_filename = None

        has_uploaded_criteria = bool(criteria_file and criteria_file.filename)
        if has_uploaded_criteria:
            criteria_filename = safe_upload_filename(criteria_file.filename) # 清洗审查要点文件名
            if not criteria_filename.lower().endswith(".docx"): # 如果审查要点文件不是 .docx 结尾，返回 400 错误
                raise HTTPException(
                    status_code=400,
                    detail="审查要点文件格式必须是 DOCX。",
                )
            selected_criteria_path = paths.stored_criteria_path(criteria_filename)
            with selected_criteria_path.open("wb") as f: # 将上传的审查要点文件保存到 API 任务目录
                shutil.copyfileobj(criteria_file.file, f)
            validate_uploaded_docx(selected_criteria_path) # 校验上传的审查要点文件是否是有效的 DOCX 文件，否则返回 400 错误
            validate_review_criteria_content(selected_criteria_path) # 校验审查要点内容是否符合系统要求，比如是否包含编号审查要点，否则返回 400 错误
            criteria_source = "uploaded"
            append_api_event(
                paths.api_events_path,
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
            criteria_snapshot_path = paths.stored_criteria_path(selected_criteria_path.name)
            shutil.copy2(selected_criteria_path, criteria_snapshot_path)
            selected_criteria_path = criteria_snapshot_path
            append_api_event(
                paths.api_events_path,
                "criteria_default_saved",
                file_path=str(selected_criteria_path),
                size_bytes=selected_criteria_path.stat().st_size,
            )

        with paths.stored_contract_path.open("wb") as f: # 将上传的合同文件保存到 API 任务目录
            shutil.copyfileobj(file.file, f) # 写入 file 
        append_api_event(
            paths.api_events_path,
            "contract_saved",
            file_path=str(paths.stored_contract_path),
            size_bytes=paths.stored_contract_path.stat().st_size,
            criteria_source=criteria_source,
        )

        validate_uploaded_docx(paths.stored_contract_path)
        append_api_event(paths.api_events_path, "docx_validation_passed")

        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=str(paths.workflow_log_dir),
            conversation_log_dir=str(paths.conversation_log_dir),
            mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
            api_events_path=str(paths.api_events_path),
        )

        append_api_event(paths.api_events_path, "review_started", task_id=paths.task_id)
        token = set_conversation_log_dir(paths.conversation_log_dir)
        try:
            async def run_workflow():
                return await workflow.run(
                    contract_path=str(paths.stored_contract_path), # API 任务目录中的合同文件路径
                    criteria_path=str(selected_criteria_path), # API 任务目录中的审查要点文件路径
                    output_path=str(paths.final_report_path), # API 任务目录中的审核结果文件路径，最终审核结果会保存在这里
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

        append_api_event(paths.api_events_path, "review_completed", result_file=str(output_path))
        response_filename = build_report_display_name(filename)
        await post_api_review_callback(
            output_path=output_path,
            response_filename=response_filename,
            meta_fields=meta_fields,
        )
        append_api_event(
            paths.api_events_path,
            "api_callback_completed",
            enabled=API_CALLBACK_ENABLED,
            url=API_CALLBACK_URL if API_CALLBACK_ENABLED else "",
            file_field=API_CALLBACK_FILE_FIELD,
            meta_fields=meta_fields,
        )
        response_headers = {
            "x-review-task-id": paths.task_id,
            "x-review-log-path": str(paths.api_events_path),
            "x-review-criteria-source": criteria_source,
        }
        for field_name, field_value in meta_fields.items():
            response_headers[_header_name_for_meta_field(field_name)] = field_value
        return FileResponse(
            path=output_path, # 返回审核结果文件
            media_type=DOCX_MEDIA_TYPE, # 设置正确的 DOCX MIME 类型
            filename=response_filename, # 设置下载文件名
            background=BackgroundTask(paths.cleanup_if_temporary),
            headers=response_headers,
        )

    except HTTPException as exc:
        append_api_event(
            paths.api_events_path,
            "review_failed",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        paths.cleanup_if_temporary()
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "task_id": paths.task_id,
                "status": "failed",
                "message": exc.detail,
                "api_events_path": str(paths.api_events_path),
            },
        )
    except Exception as exc:
        status_code = 503 if isinstance(exc, ModelCallError) else 500
        if isinstance(exc, ModelCallError):
            message = f"审核失败：{exc.user_message}"
            append_api_event(
                paths.api_events_path,
                exc.event_type,
                component=exc.component,
                error=str(exc),
            )
        else:
            message = "审核失败，请查看任务日志。"
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
        paths.cleanup_if_temporary()
        return JSONResponse(
            status_code=status_code,
            content={
                "task_id": paths.task_id,
                "status": "failed",
                "message": message,
                "api_events_path": str(paths.api_events_path),
            },
        )
    finally:
        await file.close() # 确保上传的合同文件被正确关闭，释放系统资源
        if criteria_file:
            await criteria_file.close() # 确保上传的审查要点文件被正确关闭，释放系统资源
