from __future__ import annotations

import asyncio
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import DATA_DIR, MCP_SERVER_PATH, PROJECT_ROOT, USERS_FILE
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.api_event_logger import append_api_event
from loggers.resolve_review_task_paths import resolve_review_task_paths
from loggers.review_history import (
    HISTORY_SCHEMA_VERSION,
    append_history_record,
    format_file_size,
    format_timestamp,
    load_history_records,
)
from main_workflow.main_workflow import ContractReviewWorkflow
from web.auth import find_user, load_users, normalize_role, save_users, verify_login, verify_password
from web.core.document_validation import (
    DOCX_MEDIA_TYPE,
    validate_review_criteria_content,
    validate_uploaded_docx,
)
from web.core.errors import ModelCallError
from web.core.filenames import build_report_display_name, safe_upload_filename, strip_task_file_prefix
from web.core.review_runtime import review_semaphore


templates = Jinja2Templates(directory=str(Path(PROJECT_ROOT) / "web" / "templates"))
user_router = APIRouter()
review_tasks: dict[str, dict] = {}


def get_running_task(username: str) -> dict | None:
    task = review_tasks.get(username)
    if task and task.get("status") in {"queued", "running"}:
        return task
    return None


def issue_login_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    tokens = request.session.get("login_tokens")
    if not isinstance(tokens, list):
        tokens = []
    tokens.append(token)
    request.session["login_tokens"] = tokens[-5:]
    return token


def consume_login_token(request: Request, token: str) -> bool:
    tokens = request.session.get("login_tokens")
    if not isinstance(tokens, list):
        return False
    matched = any(secrets.compare_digest(token, item) for item in tokens)
    if matched:
        request.session["login_tokens"] = [
            item for item in tokens if not secrets.compare_digest(token, item)
        ]
    return matched


def create_auth_context(request: Request, user: dict) -> str:
    ctx = secrets.token_urlsafe(16)
    contexts = request.session.get("auth_contexts")
    if not isinstance(contexts, dict):
        contexts = {}
    contexts[ctx] = {
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
        "role": normalize_role(user.get("role")),
    }
    request.session["auth_contexts"] = contexts
    return ctx


def remove_auth_contexts_for_username(request: Request, username: str) -> None:
    contexts = request.session.get("auth_contexts")
    if not isinstance(contexts, dict):
        return
    removed = False
    for ctx, context in list(contexts.items()):
        if isinstance(context, dict) and context.get("username") == username:
            contexts.pop(ctx, None)
            removed = True
    if removed:
        request.session["auth_contexts"] = contexts


def get_request_ctx(request: Request) -> str | None:
    ctx = request.query_params.get("ctx")
    if ctx:
        return ctx
    return None


def sync_context_user(request: Request) -> dict | None:
    ctx = get_request_ctx(request)
    if not ctx:
        return None
    contexts = request.session.get("auth_contexts")
    if not isinstance(contexts, dict):
        return None
    context = contexts.get(ctx)
    if not isinstance(context, dict):
        return None

    user = find_user(USERS_FILE, context.get("username", ""))
    if not user or not user.get("enabled", True):
        contexts.pop(ctx, None)
        request.session["auth_contexts"] = contexts
        return None

    context["display_name"] = user.get("display_name") or user["username"]
    context["role"] = normalize_role(user.get("role"))
    contexts[ctx] = context
    request.session["auth_contexts"] = contexts
    return {
        "ctx": ctx,
        "username": user["username"],
        "display_name": context["display_name"],
        "role": context["role"],
    }


def ctx_path(path: str, ctx: str | None) -> str:
    if not ctx:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}ctx={quote(ctx)}"


def remove_auth_context(request: Request, ctx: str | None) -> None:
    if not ctx:
        return
    contexts = request.session.get("auth_contexts")
    if not isinstance(contexts, dict):
        return
    contexts.pop(ctx, None)
    request.session["auth_contexts"] = contexts


def build_report_display_name(contract_original_name: str) -> str:
    stem = Path(contract_original_name).stem or "审核结果" # 去除文件扩展名，如果没有文件名则使用默认 "审核结果"
    return f"{stem}_批注版.docx"


def strip_task_file_prefix(filename: str | None) -> str:
    if not filename:
        return ""
    return TASK_FILE_PREFIX_RE.sub("", safe_upload_filename(filename))


def build_history_display_names(record: dict) -> tuple[str, str]:
    contract_name = (
        record.get("contract_original_name")
        or strip_task_file_prefix(record.get("contract_stored_name"))
        or "-"
    )
    report_name = record.get("report_display_name")
    if not report_name:
        report_name = (
            build_report_display_name(contract_name)
            if contract_name != "-"
            else strip_task_file_prefix(record.get("report_stored_name"))
        )
    return strip_task_file_prefix(contract_name), strip_task_file_prefix(report_name)


def build_history_record(paths, output_path: Path, task: dict) -> dict:
    contract_stat = paths.stored_contract_path.stat()
    report_stat = output_path.stat()
    criteria_source = task.get("criteria_source", "default")
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "task_id": paths.task_id,
        "status": "completed",
        "contract_original_name": paths.original_filename,
        "contract_stored_name": paths.stored_contract_path.name,
        "contract_size_bytes": contract_stat.st_size,
        "contract_uploaded_at": task.get("contract_uploaded_at") or format_timestamp(contract_stat.st_mtime),
        "criteria_source": criteria_source,
        "criteria_original_name": task.get("criteria_original_name") if criteria_source == "uploaded" else None,
        "report_display_name": build_report_display_name(paths.original_filename),
        "report_stored_name": output_path.name,
        "report_size_bytes": report_stat.st_size,
        "report_created_at": format_timestamp(report_stat.st_mtime),
    }


async def run_review_task(username: str, paths, criteria_path: Path) -> None:
    task = review_tasks[username]
    task["status"] = "running"
    task["message"] = "正在审核。"

    token = set_conversation_log_dir(paths.conversation_log_dir)
    try:
        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=str(paths.workflow_log_dir),
            conversation_log_dir=str(paths.conversation_log_dir),
            mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
            api_events_path=str(paths.api_events_path),
        )

        append_api_event(paths.api_events_path, "review_started", task_id=paths.task_id)

        async def run_workflow():
            return await workflow.run(
                contract_path=str(paths.stored_contract_path),
                criteria_path=str(criteria_path),
                output_path=str(paths.final_report_path),
            )

        if review_semaphore is None:
            result = await run_workflow()
        else:
            async with review_semaphore:
                result = await run_workflow()

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise RuntimeError("未找到输出的 DOCX 文件。")

        task["status"] = "completed"
        task["message"] = "审核完成。"
        task["result_name"] = output_path.name
        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_history_record(
            Path(DATA_DIR),
            username,
            build_history_record(paths, output_path, task),
        )
        append_api_event(paths.api_events_path, "review_completed", result_file=str(output_path))
    except Exception as exc:
        task["status"] = "failed"
        if isinstance(exc, ModelCallError):
            task["message"] = f"审核失败：{exc.user_message}"
            append_api_event(
                paths.api_events_path,
                exc.event_type,
                component=exc.component,
                error=str(exc),
            )
        else:
            task["message"] = "审核失败，请查看任务日志。"
        task["error"] = str(exc)
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
    finally:
        reset_conversation_log_dir(token)


def get_current_username(request: Request) -> str | None:
    user = sync_context_user(request)
    if not user:
        return None
    return user["username"]


def require_current_username(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(
            status_code=401, 
            detail="未登录。"
        )
    return username


@user_router.get("/session/status")
async def session_status(request: Request):
    user = sync_context_user(request)
    if not user and not get_request_ctx(request):
        contexts = request.session.get("auth_contexts")
        if isinstance(contexts, dict):
            for ctx in list(contexts):
                context = contexts.get(ctx)
                if not isinstance(context, dict):
                    continue
                stored_user = find_user(USERS_FILE, context.get("username", ""))
                if stored_user and stored_user.get("enabled", True):
                    return {
                        "active": True,
                        "role": normalize_role(stored_user.get("role")),
                    }
    if not user:
        return JSONResponse({"active": False}, status_code=401)
    return {"active": True, "role": user["role"]}


def update_display_name(users_file: str | Path, username: str, display_name: str) -> str:
    cleaned = display_name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="显示名称不能为空。")
    if len(cleaned) > 40:
        raise HTTPException(status_code=400, detail="显示名称不能超过 40 个字符。")

    users = load_users(users_file)
    for user in users:
        if user.get("username") == username:
            user["display_name"] = cleaned
            save_users(users_file, users)
            return cleaned

    raise HTTPException(status_code=404, detail="未找到当前用户。")


def list_history(username: str) -> list[dict]:
    data_dir = Path(DATA_DIR)
    user_root = data_dir / username
    rows = []
    for record in load_history_records(data_dir, username):
        report_stored_name = record.get("report_stored_name")
        if not report_stored_name:
            continue
        report_path = user_root / "reports_docx" / safe_upload_filename(report_stored_name)
        if not report_path.exists():
            continue

        criteria_source = record.get("criteria_source")
        criteria_label = "默认审查要点"
        if criteria_source == "uploaded":
            criteria_label = f"本次上传：{record.get('criteria_original_name') or '-'}"

        contract_display_name, report_display_name = build_history_display_names(record)
        rows.append({
            **record,
            "contract_display_name": contract_display_name,
            "report_display_name": report_display_name,
            "contract_size": format_file_size(record.get("contract_size_bytes")),
            "report_size": format_file_size(record.get("report_size_bytes")),
            "criteria_label": criteria_label,
            "download_name": report_path.name,
        })
    rows.sort(key=lambda item: item.get("report_created_at") or "", reverse=True)
    return rows[:20]


@user_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    login_token = issue_login_token(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "login_token": login_token,
        },
    )


@user_router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    login_token: str = Form(...),
):
    if not consume_login_token(request, login_token):
        return RedirectResponse("/login", status_code=303)

    next_login_token = issue_login_token(request)
    existing_user = find_user(USERS_FILE, username)
    if (
        existing_user
        and verify_password(password, existing_user.get("password_hash", ""))
        and not existing_user.get("enabled", True)
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "账号已被禁用，请联系管理员。",
                "login_token": next_login_token,
            },
            status_code=403,
        )

    user = verify_login(USERS_FILE, username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "用户名或密码错误。",
                "login_token": next_login_token,
            },
            status_code=401,
        )

    remove_auth_contexts_for_username(request, user["username"])
    ctx = create_auth_context(request, user)
    if normalize_role(user.get("role")) == "admin":
        return RedirectResponse(ctx_path("/admin", ctx), status_code=303)
    return RedirectResponse(ctx_path("/work", ctx), status_code=303)


@user_router.post("/logout")
async def logout(request: Request):
    remove_auth_context(request, get_request_ctx(request))
    return RedirectResponse("/login", status_code=303)


@user_router.post("/profile/display-name")
async def update_profile_display_name(
    request: Request,
    display_name: str = Form(...),
):
    username = get_current_username(request)
    ctx = get_request_ctx(request)
    if not username:
        return RedirectResponse("/login", status_code=303)

    try:
        cleaned = update_display_name(USERS_FILE, username, display_name)
        request.session["display_name"] = cleaned
        request.session["flash_success"] = "显示名称已更新。"
    except HTTPException as exc:
        request.session["flash_error"] = exc.detail
    except OSError:
        request.session["flash_error"] = "显示名称更新失败，请检查用户配置文件是否可写。"
    return RedirectResponse(ctx_path("/settings", ctx), status_code=303)


@user_router.get("/", response_class=HTMLResponse)
async def entry_page(request: Request):
    login_token = issue_login_token(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "login_token": login_token,
        },
    )


@user_router.get("/work", response_class=HTMLResponse)
async def index(request: Request):
    user = sync_context_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303) # happens when user tries to access /work without logging in, redirect them to login page
    if user["role"] == "admin":
        return RedirectResponse(ctx_path("/admin", user["ctx"]), status_code=303)
    username = user["username"]
    task = review_tasks.get(username)
    error = request.session.pop("flash_error", None)
    success = request.session.pop("flash_success", None)
    result_name = None
    if task:
        if task.get("status") == "failed":
            error = task.get("message") or error
        elif task.get("status") == "completed":
            result_name = task.get("result_name")
            review_tasks.pop(username, None)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "username": username,
            "display_name": user["display_name"],
            "ctx": user["ctx"],
            "history": list_history(username),
            "error": error,
            "success": success,
            "result_name": result_name,
            "active_task": get_running_task(username),
        },
    )


@user_router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    user = sync_context_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] == "admin":
        return RedirectResponse(ctx_path("/admin", user["ctx"]), status_code=303)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "username": user["username"],
            "display_name": user["display_name"],
            "ctx": user["ctx"],
            "error": request.session.pop("flash_error", None),
            "success": request.session.pop("flash_success", None),
        },
    )


@user_router.post("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
    username = get_current_username(request)
    ctx = get_request_ctx(request)
    if not username:
        return RedirectResponse("/login", status_code=303)

    if get_running_task(username):
        request.session["flash_error"] = "已有审核任务正在运行，请等待完成后再提交。"
        await file.close()
        if criteria_file:
            await criteria_file.close()
        return RedirectResponse(ctx_path("/work", ctx), status_code=303)

    filename = safe_upload_filename(file.filename)
    paths = resolve_review_task_paths(
        username=username,
        original_filename=filename,
        data_dir=Path(DATA_DIR),
    )

    try:
        paths.ensure_task_dirs() # create necessary directories
        # api event I - file received for review, with metadata of username and filename (after sanitization)
        append_api_event(
            paths.api_events_path,
            "upload_received",
            username=username,
            filename=filename
        )

        if not filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=400, 
                detail="系统支持的文件格式是 DOCX 哦~"
            )
        selected_criteria_path = paths.criteria_path
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
            with paths.uploaded_criteria_path.open("wb") as f:
                shutil.copyfileobj(criteria_file.file, f)
            validate_uploaded_docx(paths.uploaded_criteria_path) 
            validate_review_criteria_content(paths.uploaded_criteria_path)
            selected_criteria_path = paths.uploaded_criteria_path
            criteria_source = "uploaded"

            append_api_event(
                paths.api_events_path,
                "criteria_uploaded",
                file_path=str(paths.uploaded_criteria_path),
                original_filename=criteria_filename,
                size_bytes=paths.uploaded_criteria_path.stat().st_size,
            )
        elif not paths.criteria_path.exists():
            request.session["flash_error"] = f"未找到审查要点文件：{paths.criteria_path}"
            return RedirectResponse(ctx_path("/work", ctx), status_code=303)
        with paths.stored_contract_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        
        # api event II - file saved and ready for validation and review
        append_api_event(
            paths.api_events_path,
            "contract_saved",
            file_path=str(paths.stored_contract_path),
            size_bytes=paths.stored_contract_path.stat().st_size,
        )

        validate_uploaded_docx(paths.stored_contract_path) # Check if the uploaded file is a valid .docx file, otherwise raise HTTPException with 400 status code and error message.

        # api event III - file passed validation and review is about to start
        append_api_event(
            paths.api_events_path, 
            "docx_validation_passed"
        )

        # This is where review_tasks is written within
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        review_tasks[username] = {
            "status": "queued",
            "message": "审核任务已排队。",
            "task_id": paths.task_id,
            "filename": filename,
            "criteria_source": criteria_source,
            "criteria_original_name": criteria_filename,
            "contract_uploaded_at": created_at,
            "created_at": created_at,
        }
        # This is where Semaphore comes into play.
        asyncio.create_task(run_review_task(username, paths, selected_criteria_path))
        return RedirectResponse(ctx_path("/work", ctx), status_code=303)

    except HTTPException as exc:
        append_api_event(paths.api_events_path, "review_failed", status_code=exc.status_code, detail=exc.detail)
        request.session["flash_error"] = exc.detail
        return RedirectResponse(ctx_path("/work", ctx), status_code=303)
    except Exception as exc:
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
        request.session["flash_error"] = "审核失败，请查看任务日志。"
        return RedirectResponse(ctx_path("/work", ctx), status_code=303)
    finally:
        await file.close()
        if criteria_file:
            await criteria_file.close()


@user_router.get("/download/{filename}")
async def download_result(request: Request, filename: str):
    username = require_current_username(request)
    safe_name = safe_upload_filename(filename)
    path = Path(DATA_DIR) / username / "reports_docx" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="未找到审核结果文件。")
    return FileResponse(
        path,
        media_type=DOCX_MEDIA_TYPE,
        filename=safe_name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
    )


@user_router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    user = sync_context_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] == "admin":
        return RedirectResponse(ctx_path("/admin", user["ctx"]), status_code=303)
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "username": user["username"],
            "display_name": user["display_name"],
            "ctx": user["ctx"],
            "history": list_history(user["username"]),
        },
    )
