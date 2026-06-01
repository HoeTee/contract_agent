from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from config import DATA_DIR, DEFAULT_REVIEW_CRITERIA_PATH, PROJECT_ROOT
from web.admin_services import (
    admin_summary,
    get_admin_user,
    get_user_criteria_info,
    list_admin_users,
    list_user_log_tasks,
    list_user_review_history,
)
from web.routes import DOCX_MEDIA_TYPE, safe_upload_filename, validate_review_criteria_content, validate_uploaded_docx
from services.user_management import (
    UserManagementError,
    create_user_account,
    delete_user_account,
    reset_user_password,
    set_user_enabled,
    set_user_role,
)


templates = Jinja2Templates(directory=str(Path(PROJECT_ROOT) / "web" / "templates"))
admin_router = APIRouter(prefix="/admin")


def is_current_admin(request: Request) -> bool:
    return request.session.get("role") == "admin"


def require_admin(request: Request) -> None:
    if not request.session.get("username"):
        raise HTTPException(status_code=401, detail="未登录。")
    if not is_current_admin(request):
        raise HTTPException(status_code=403, detail="无管理员权限。")


def admin_template_context(request: Request, **extra) -> dict:
    return {
        "username": request.session.get("username"),
        "display_name": request.session.get("display_name") or request.session.get("username"),
        **extra,
    }


def admin_user_redirect(username: str) -> RedirectResponse:
    return RedirectResponse(f"/admin/users/{quote(username)}", status_code=303)


def set_admin_flash(request: Request, *, success: str | None = None, error: str | None = None) -> None:
    if success:
        request.session["admin_flash_success"] = success
    if error:
        request.session["admin_flash_error"] = error


@admin_router.get("", response_class=HTMLResponse)
async def admin_index(request: Request):
    try:
        require_admin(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        raise

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        admin_template_context(request, summary=admin_summary()),
    )


@admin_router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    require_admin(request)
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        admin_template_context(
            request,
            users=list_admin_users(),
            error=request.session.pop("admin_flash_error", None),
            success=request.session.pop("admin_flash_success", None),
        ),
    )


@admin_router.post("/users/create")
async def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
    role: str = Form("user"),
):
    require_admin(request)
    try:
        created = create_user_account(
            username=username,
            password=password,
            display_name=display_name,
            role=role,
        )
        set_admin_flash(request, success=f"已创建用户：{created}")
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
    return RedirectResponse("/admin/users", status_code=303)


@admin_router.get("/users/{target_username}", response_class=HTMLResponse)
async def admin_user_detail(request: Request, target_username: str):
    require_admin(request)
    user = get_admin_user(target_username)
    if not user:
        raise HTTPException(status_code=404, detail="未找到用户。")

    error = request.session.pop("admin_flash_error", None)
    success = request.session.pop("admin_flash_success", None)
    return templates.TemplateResponse(
        request,
        "admin_user_detail.html",
        admin_template_context(
            request,
            target_user=user,
            history=list_user_review_history(target_username),
            criteria=get_user_criteria_info(target_username),
            logs=list_user_log_tasks(target_username),
            error=error,
            success=success,
        ),
    )


@admin_router.post("/users/{target_username}/role")
async def admin_set_user_role(
    request: Request,
    target_username: str,
    role: str = Form(...),
):
    require_admin(request)
    if target_username == request.session.get("username") and role != "admin":
        set_admin_flash(request, error="不能移除当前管理员自己的管理员角色。")
        return admin_user_redirect(target_username)
    try:
        updated_role = set_user_role(username=target_username, role=role)
        set_admin_flash(request, success=f"已更新用户角色：{updated_role}")
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
    return admin_user_redirect(target_username)


@admin_router.post("/users/{target_username}/password")
async def admin_reset_user_password(
    request: Request,
    target_username: str,
    password: str = Form(...),
):
    require_admin(request)
    try:
        reset_user_password(username=target_username, password=password)
        set_admin_flash(request, success="已重置用户密码。")
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
    return admin_user_redirect(target_username)


@admin_router.post("/users/{target_username}/enable")
async def admin_enable_user(request: Request, target_username: str):
    require_admin(request)
    try:
        set_user_enabled(username=target_username, enabled=True)
        set_admin_flash(request, success="已启用用户。")
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
    return admin_user_redirect(target_username)


@admin_router.post("/users/{target_username}/disable")
async def admin_disable_user(request: Request, target_username: str):
    require_admin(request)
    if target_username == request.session.get("username"):
        set_admin_flash(request, error="不能禁用当前登录的管理员账号。")
        return admin_user_redirect(target_username)
    try:
        set_user_enabled(username=target_username, enabled=False)
        set_admin_flash(request, success="已禁用用户。")
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
    return admin_user_redirect(target_username)


@admin_router.post("/users/{target_username}/delete")
async def admin_delete_user(
    request: Request,
    target_username: str,
    keep_data: bool = Form(False),
):
    require_admin(request)
    if target_username == request.session.get("username"):
        set_admin_flash(request, error="不能删除当前登录的管理员账号。")
        return admin_user_redirect(target_username)
    try:
        delete_user_account(username=target_username, keep_data=keep_data)
        set_admin_flash(request, success=f"已删除用户：{target_username}")
        return RedirectResponse("/admin/users", status_code=303)
    except UserManagementError as exc:
        set_admin_flash(request, error=str(exc))
        return admin_user_redirect(target_username)


@admin_router.get("/users/{target_username}/criteria/download")
async def admin_download_user_criteria(request: Request, target_username: str):
    require_admin(request)
    user = get_admin_user(target_username)
    if not user:
        raise HTTPException(status_code=404, detail="未找到用户。")

    path = Path(DATA_DIR) / target_username / "contract_review_criteria" / "criteria.docx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="未找到用户默认审查要点。")
    return FileResponse(
        path,
        media_type=DOCX_MEDIA_TYPE,
        filename=f"{target_username}_criteria.docx",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(target_username)}_criteria.docx"},
    )


@admin_router.post("/users/{target_username}/criteria/upload")
async def admin_upload_user_criteria(
    request: Request,
    target_username: str,
    criteria_file: UploadFile = File(...),
):
    require_admin(request)
    if not get_admin_user(target_username):
        raise HTTPException(status_code=404, detail="未找到用户。")

    try:
        filename = safe_upload_filename(criteria_file.filename)
        if not filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="审查要点文件格式必须是 DOCX。")

        target_path = Path(DATA_DIR) / target_username / "contract_review_criteria" / "criteria.docx"
        temp_path = target_path.with_name("criteria.upload.tmp.docx")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("wb") as f:
            shutil.copyfileobj(criteria_file.file, f)
        validate_uploaded_docx(temp_path)
        validate_review_criteria_content(temp_path)
        temp_path.replace(target_path)
        request.session["admin_flash_success"] = "用户默认审查要点已更新。"
    except HTTPException as exc:
        request.session["admin_flash_error"] = exc.detail
    except Exception:
        request.session["admin_flash_error"] = "审查要点更新失败。"
    finally:
        temp_path = Path(DATA_DIR) / target_username / "contract_review_criteria" / "criteria.upload.tmp.docx"
        if temp_path.exists():
            temp_path.unlink()
        await criteria_file.close()
    return admin_user_redirect(target_username)


@admin_router.post("/users/{target_username}/criteria/restore")
async def admin_restore_user_criteria(request: Request, target_username: str):
    require_admin(request)
    if not get_admin_user(target_username):
        raise HTTPException(status_code=404, detail="未找到用户。")

    default_path = Path(DEFAULT_REVIEW_CRITERIA_PATH)
    target_path = Path(DATA_DIR) / target_username / "contract_review_criteria" / "criteria.docx"
    try:
        if not default_path.exists():
            raise HTTPException(status_code=404, detail="未找到系统默认审查要点。")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_path, target_path)
        request.session["admin_flash_success"] = "已恢复系统默认审查要点。"
    except HTTPException as exc:
        request.session["admin_flash_error"] = exc.detail
    except Exception:
        request.session["admin_flash_error"] = "恢复默认审查要点失败。"
    return admin_user_redirect(target_username)


@admin_router.get("/users/{target_username}/logs/{date}/{task_name}/api-events")
async def admin_view_api_events(request: Request, target_username: str, date: str, task_name: str):
    require_admin(request)
    if not get_admin_user(target_username):
        raise HTTPException(status_code=404, detail="未找到用户。")

    logs_root = (Path(DATA_DIR) / target_username / "logs").resolve()
    path = (logs_root / safe_upload_filename(date) / safe_upload_filename(task_name) / "api_events.jsonl").resolve()
    if logs_root not in path.parents:
        raise HTTPException(status_code=400, detail="日志路径不合法。")
    if not path.exists():
        raise HTTPException(status_code=404, detail="未找到 API 事件日志。")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
