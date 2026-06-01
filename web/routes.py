from __future__ import annotations

import asyncio
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import DATA_DIR, MAX_API_CONCURRENT_REVIEWS, MCP_SERVER_PATH, USERS_FILE
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.api_event_logger import append_api_event
from loggers.resolve_review_task_paths import resolve_review_task_paths
from main_workflow.main_workflow import ContractReviewWorkflow
from web.auth import verify_login


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OLE_DOC_SIGNATURE = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")
REQUIRED_DOCX_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
}

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "web" / "templates"))
router = APIRouter()
review_tasks: dict[str, dict] = {}
review_semaphore = (
    asyncio.Semaphore(MAX_API_CONCURRENT_REVIEWS)
    if MAX_API_CONCURRENT_REVIEWS > 0
    else None # It could be None if MAX_API_CONCURRENT_REVIEWS is not set, meaning no concurrency limit.
)


def get_running_task(username: str) -> dict | None:
    task = review_tasks.get(username)
    if task and task.get("status") in {"queued", "running"}:
        return task
    return None


async def run_review_task(username: str, paths, criteria_path: Path) -> None:
    task = review_tasks[username]
    task["status"] = "running"
    task["message"] = "Review is running."

    token = set_conversation_log_dir(paths.conversation_log_dir)
    try:
        workflow = ContractReviewWorkflow(
            server_script_path=str(MCP_SERVER_PATH),
            workflow_log_dir=str(paths.workflow_log_dir),
            conversation_log_dir=str(paths.conversation_log_dir),
            mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
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
            raise RuntimeError("Output DOCX was not found.")

        task["status"] = "completed"
        task["message"] = "Review completed."
        task["result_name"] = output_path.name
        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_api_event(paths.api_events_path, "review_completed", result_file=str(output_path))
    except Exception as exc:
        task["status"] = "failed"
        task["message"] = "Review failed. Check the task logs."
        task["error"] = str(exc)
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
    finally:
        reset_conversation_log_dir(token)


def safe_upload_filename(filename: str | None) -> str:
    if not filename:
        return "uploaded.docx"
    return Path(filename.replace("\\", "/")).name


def get_current_username(request: Request) -> str | None:
    return request.session.get("username")


def require_current_username(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated"
        )
    return username


def validate_uploaded_docx(path: Path) -> None:
    with path.open("rb") as f:
        header = f.read(8)

    if header.startswith(OLE_DOC_SIGNATURE): # Check for legacy .doc/OLE signature
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file is a legacy .doc/OLE document, not a real .docx file. "
                "Please convert it to .docx with Word or LibreOffice before uploading."
            ),
        )

    if not zipfile.is_zipfile(path): # Check if it's a valid ZIP file (basic check for .docx structure)
        raise HTTPException(
            status_code=400, 
            detail="The uploaded file is not a valid .docx ZIP package."
        )

    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile: # If the file is not a valid ZIP archive, treat it as an invalid .docx
        raise HTTPException(
            status_code=400, 
            detail="The uploaded file is not a valid .docx ZIP package."
        )

    missing_parts = sorted(REQUIRED_DOCX_PARTS - names)
    if missing_parts: # Check for required .docx parts to ensure it's not just any ZIP file
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file has a .docx extension, but its internal structure "
                f"is not a valid Word DOCX package. Missing parts: {missing_parts}"
            ),
        )


def list_history(username: str) -> list[dict]:
    report_dir = Path(DATA_DIR) / username / "reports_docx" # Pathlib object
    contract_dir = Path(DATA_DIR) / username / "contracts" # Pathlib object
    if not report_dir.exists():
        return []

    rows = []
    # p.stat() obtains file metadata; p.stat().st_mtime gives the last modification time of the file.
    # p is a Pathlib object.
    for report in sorted(report_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True):  
        prefix = "_".join(report.name.split("_")[:3])
        contract = next(contract_dir.glob(f"{prefix}_*.docx"), None) if contract_dir.exists() else None # next() retrieves the first item from the list of Pathlib objects
        rows.append({
            "report_name": report.name,
            "contract_name": contract.name if contract else "",
            "mtime": report.stat().st_mtime,
        })
    return rows[:20] # Return the 20 most recent reports metadata. 


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    request.session.clear()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...)
):
    user = verify_login(USERS_FILE, username, password) # obtain user dict of metdata if login is successful, otherwise None
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "用户名或密码错误哦~"},
            status_code=401, # Return 401 unauthorized for failed login attempts
        )

    request.session["username"] = user["username"]
    request.session["display_name"] = user.get("display_name") or user["username"]
    return RedirectResponse("/work", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def entry_page(request: Request):
    request.session.clear()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
        },
    )


@router.get("/work", response_class=HTMLResponse)
async def index(request: Request):
    username = get_current_username(request)
    if not username:
        return RedirectResponse("/login", status_code=303) # happens when user tries to access /work without logging in, redirect them to login page
    task = review_tasks.get(username)
    error = request.session.pop("flash_error", None)
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
            "display_name": request.session.get("display_name", username),
            "history": list_history(username),
            "error": error,
            "result_name": result_name,
            "active_task": get_running_task(username),
        },
    )


@router.post("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    file: UploadFile = File(...),
    criteria_file: UploadFile | None = File(None),
):
    username = get_current_username(request)
    if not username:
        return RedirectResponse("/login", status_code=303)

    if get_running_task(username):
        request.session["flash_error"] = "A review is already running. Please wait for it to finish."
        await file.close()
        if criteria_file:
            await criteria_file.close()
        return RedirectResponse("/work", status_code=303)

    filename = safe_upload_filename(file.filename)
    paths = resolve_review_task_paths(
        username=username,
        original_filename=filename,
        data_dir=Path(DATA_DIR),
    )
    paths.ensure_task_dirs() # create necessary directories
    # api event I - file received for review, with metadata of username and filename (after sanitization)
    append_api_event(
        paths.api_events_path, 
        "upload_received", 
        username=username, 
        filename=filename
    )

    try:
        if not filename.lower().endswith(".docx"):
            raise HTTPException(
                status_code=400, 
                detail="系统支持的文件格式是 DOCX 哦~"
            )
        selected_criteria_path = paths.criteria_path
        criteria_source = "default"
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
            request.session["flash_error"] = f"Review criteria file was not found: {paths.criteria_path}"
            return RedirectResponse("/work", status_code=303)
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
        review_tasks[username] = {
            "status": "queued",
            "message": "Review is queued.",
            "task_id": paths.task_id,
            "filename": filename,
            "criteria_source": criteria_source,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        # This is where Semaphore comes into play.
        asyncio.create_task(run_review_task(username, paths, selected_criteria_path))
        return RedirectResponse("/work", status_code=303)

    except HTTPException as exc:
        append_api_event(paths.api_events_path, "review_failed", status_code=exc.status_code, detail=exc.detail)
        request.session["flash_error"] = exc.detail
        return RedirectResponse("/work", status_code=303)
    except Exception as exc:
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
        request.session["flash_error"] = "Review failed. Check the task logs."
        return RedirectResponse("/work", status_code=303)
    finally:
        await file.close()
        if criteria_file:
            await criteria_file.close()


@router.get("/download/{filename}")
async def download_result(request: Request, filename: str):
    username = require_current_username(request)
    safe_name = safe_upload_filename(filename)
    path = Path(DATA_DIR) / username / "reports_docx" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file was not found.")
    return FileResponse(
        path,
        media_type=DOCX_MEDIA_TYPE,
        filename=safe_name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
    )


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    username = get_current_username(request)
    if not username:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "username": username,
            "display_name": request.session.get("display_name", username),
            "history": list_history(username),
        },
    )
