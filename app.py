import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Response, UploadFile

from main_workflow.main_workflow import ContractReviewWorkflow


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_TMP_DIR = PROJECT_ROOT / "runtime_temp"
REVIEWS_TMP_DIR = RUNTIME_TMP_DIR / "reviews"

CRITERIA_PATH = PROJECT_ROOT / "docs" / "contract_review_criteria" / "审核要点（初稿）(2).docx"
MCP_SERVER_PATH = PROJECT_ROOT / "mcp_service" / "mcp_server" / "mcp_server.py"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def reset_runtime_temp_dir() -> None:
    if REVIEWS_TMP_DIR.exists():
        shutil.rmtree(REVIEWS_TMP_DIR)
    REVIEWS_TMP_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    reset_runtime_temp_dir()
    yield
    reset_runtime_temp_dir()


app = FastAPI(
    title="Contract Review API",
    description="API for uploading contracts and receiving review results.",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


def safe_upload_filename(filename: str | None) -> str:
    safe_name = Path(filename.replace("\\", "/")).name # This processes various dir separators and ensures we only get the final filename
    return safe_name

@app.post("/review")
async def review_contract(file: UploadFile = File(...)):
    filename = safe_upload_filename(file.filename) # file.filename is the filename
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported.")

    if not CRITERIA_PATH.exists():
        raise HTTPException(status_code=500, detail="Review criteria file was not found.")

    request_dir = REVIEWS_TMP_DIR / uuid.uuid4().hex
    request_dir.mkdir(parents=True, exist_ok=False)

    try:
        input_path = request_dir / filename
        with input_path.open("wb") as f:
            shutil.copyfileobj(file.file, f) # file.file is the actual file content

        workflow = ContractReviewWorkflow(server_script_path=str(MCP_SERVER_PATH))
        result = await workflow.run(
            contract_path=str(input_path),
            criteria_path=str(CRITERIA_PATH),
            output_dir=str(request_dir),
        )

        output_path = Path(result["report_docx"])
        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Output DOCX was not found.")

        content = output_path.read_bytes()
        output_name = output_path.name

        return Response(
            content=content, # download content of the generated DOCX file at the dir where you send the request
            media_type=DOCX_MEDIA_TYPE,
            headers={
                "Content-Disposition": (
                    "attachment; "
                    f"filename*=UTF-8''{quote(output_name)}"
                )
            },
        )
    finally:
        await file.close()
        shutil.rmtree(request_dir, ignore_errors=True)
