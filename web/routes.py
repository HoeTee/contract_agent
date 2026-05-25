from __future__ import annotations

import asyncio
import shutil
import zipfile
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
review_semaphore = (
    asyncio.Semaphore(MAX_API_CONCURRENT_REVIEWS)
    if MAX_API_CONCURRENT_REVIEWS > 0
    else None
)


def safe_upload_filename(filename: str | None) -> str:
    if not filename:
        return "uploaded.docx"
    return Path(filename.replace("\\", "/")).name


def get_current_username(request: Request) -> str | None:
    return request.session.get("username")


def require_current_username(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username


def validate_uploaded_docx(path: Path) -> None:
    with path.open("rb") as f:
        header = f.read(8)

    if header.startswith(OLE_DOC_SIGNATURE):
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file is a legacy .doc/OLE document, not a real .docx file. "
                "Please convert it to .docx with Word or LibreOffice before uploading."
            ),
        )

    if not zipfile.is_zipfile(path):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid .docx ZIP package.")

    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid .docx ZIP package.")

    missing_parts = sorted(REQUIRED_DOCX_PARTS - names)
    if missing_parts:
        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file has a .docx extension, but its internal structure "
                f"is not a valid Word DOCX package. Missing parts: {missing_parts}"
            ),
        )


def list_history(username: str) -> list[dict]:
    report_dir = Path(DATA_DIR) / username / "reports_docx"
    contract_dir = Path(DATA_DIR) / username / "contracts"
    if not report_dir.exists():
        return []

    rows = []
    for report in sorted(report_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True):
        prefix = "_".join(report.name.split("_")[:3])
        contract = next(contract_dir.glob(f"{prefix}_*.docx"), None) if contract_dir.exists() else None
        rows.append({
            "report_name": report.name,
            "contract_name": contract.name if contract else "",
            "mtime": report.stat().st_mtime,
        })
    return rows[:20]


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    username = get_current_username(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "username": username,
            "display_name": request.session.get("display_name", username) if username else None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = verify_login(USERS_FILE, username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password."},
            status_code=401,
        )

    request.session["username"] = user["username"]
    request.session["display_name"] = user.get("display_name") or user["username"]
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    username = get_current_username(request)
    if not username:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "username": username,
            "display_name": request.session.get("display_name", username),
            "history": list_history(username),
            "error": None,
            "result_name": None,
        },
    )


@router.post("/review", response_class=HTMLResponse)
async def review_page(request: Request, file: UploadFile = File(...)):
    username = get_current_username(request)
    if not username:
        return RedirectResponse("/login", status_code=303)

    filename = safe_upload_filename(file.filename)
    paths = resolve_review_task_paths(
        username=username,
        original_filename=filename,
        data_dir=Path(DATA_DIR),
    )
    paths.ensure_task_dirs()
    append_api_event(paths.api_events_path, "upload_received", username=username, filename=filename)

    try:
        if not filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Only .docx files are supported.")
        if not paths.criteria_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Review criteria file was not found: {paths.criteria_path}",
            )

        with paths.stored_contract_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        append_api_event(
            paths.api_events_path,
            "contract_saved",
            file_path=str(paths.stored_contract_path),
            size_bytes=paths.stored_contract_path.stat().st_size,
        )

        validate_uploaded_docx(paths.stored_contract_path)
        append_api_event(paths.api_events_path, "docx_validation_passed")

        token = set_conversation_log_dir(paths.conversation_log_dir)
        try:
            workflow = ContractReviewWorkflow(
                server_script_path=str(MCP_SERVER_PATH),
                workflow_log_dir=str(paths.workflow_log_dir),
                conversation_log_dir=str(paths.conversation_log_dir),
                mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
            )
            append_api_event(paths.api_events_path, "review_started", task_id=paths.task_id)
            if review_semaphore is None:
                result = await workflow.run(
                    contract_path=str(paths.stored_contract_path),
                    criteria_path=str(paths.criteria_path),
                    output_path=str(paths.final_report_path),
                )
            else:
                async with review_semaphore:
                    result = await workflow.run(
                        contract_path=str(paths.stored_contract_path),
                        criteria_path=str(paths.criteria_path),
                        output_path=str(paths.final_report_path),
                    )
        finally:
            reset_conversation_log_dir(token)

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Output DOCX was not found.")

        append_api_event(paths.api_events_path, "review_completed", result_file=str(output_path))

        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "username": username,
                "display_name": request.session.get("display_name", username),
                "history": list_history(username),
                "error": None,
                "result_name": output_path.name,
            },
        )
    except HTTPException as exc:
        append_api_event(paths.api_events_path, "review_failed", status_code=exc.status_code, detail=exc.detail)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "username": username,
                "display_name": request.session.get("display_name", username),
                "history": list_history(username),
                "error": exc.detail,
                "result_name": None,
            },
            status_code=exc.status_code,
        )
    except Exception as exc:
        append_api_event(paths.api_events_path, "review_failed", error=repr(exc))
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "username": username,
                "display_name": request.session.get("display_name", username),
                "history": list_history(username),
                "error": "Review failed. Check the task logs.",
                "result_name": None,
            },
            status_code=500,
        )
    finally:
        await file.close()


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
