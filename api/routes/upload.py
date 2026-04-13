import os
import shutil
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException

from tools.document.file_cleaner import clean_docx

router = APIRouter(prefix="/upload", tags=["upload"])

# Upload storage directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _normalize_uploaded_docx(file_path: str) -> None:
    """Persist a cleaned DOCX in place so downstream parsing/export use the same base file."""
    clean_path = clean_docx(file_path)
    try:
        shutil.copyfile(clean_path, file_path)
    finally:
        if clean_path != file_path and os.path.exists(clean_path):
            os.unlink(clean_path)


@router.post("/contract")
async def upload_contract(file: UploadFile = File(...)):
    """Upload contract file"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)

    if ext.lower() == ".docx":
        try:
            _normalize_uploaded_docx(file_path)
        except Exception as exc:
            if os.path.exists(file_path):
                os.unlink(file_path)
            raise HTTPException(status_code=400, detail=f"Failed to clean DOCX contract: {exc}") from exc

    return {
        "success": True,
        "message": "Contract uploaded successfully",
        "data": {
            "file_path": file_path,
            "original_filename": file.filename,
            "file_size": len(content)
        }
    }


@router.post("/criteria")
async def upload_criteria(file: UploadFile = File(...)):
    """Upload criteria file"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)

    if ext.lower() == ".docx":
        try:
            _normalize_uploaded_docx(file_path)
        except Exception as exc:
            if os.path.exists(file_path):
                os.unlink(file_path)
            raise HTTPException(status_code=400, detail=f"Failed to clean DOCX criteria: {exc}") from exc

    return {
        "success": True,
        "message": "Criteria uploaded successfully",
        "data": {
            "file_path": file_path,
            "original_filename": file.filename,
            "file_size": len(content)
        }
    }
