import os
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime

router = APIRouter(prefix="/upload", tags=["upload"])

# Upload storage directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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

    return {
        "success": True,
        "message": "Criteria uploaded successfully",
        "data": {
            "file_path": file_path,
            "original_filename": file.filename,
            "file_size": len(content)
        }
    }