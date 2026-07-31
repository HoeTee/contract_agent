from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from config import (
    API_RESULT_UPLOAD_AUTHORIZATION,
    API_RESULT_UPLOAD_DOMAIN,
    API_RESULT_UPLOAD_PATH,
    API_RESULT_UPLOAD_TIMEOUT_SECONDS,
)
from endpoints.runtime.document_validation import DOCX_MEDIA_TYPE


URL_KEYS = {
    "url",
    "file_url",
    "fileurl",
    "fileUrl",
    "download_url",
    "downloadUrl",
}


class ResultUploadError(Exception):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


def _build_result_upload_url() -> str:
    if not API_RESULT_UPLOAD_DOMAIN:
        raise HTTPException(status_code=500, detail="api.result_upload_domain is not configured.")
    if not API_RESULT_UPLOAD_PATH:
        raise HTTPException(status_code=500, detail="api.result_upload_path is not configured.")
    return f"{API_RESULT_UPLOAD_DOMAIN.rstrip('/')}/{API_RESULT_UPLOAD_PATH.lstrip('/')}"


def _find_url(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in URL_KEYS and isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            found = _find_url(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_url(item)
            if found:
                return found
    return None


def extract_uploaded_url(payload: Any) -> str:
    url = _find_url(payload)
    if not url:
        raise ResultUploadError("Result upload response did not contain a file URL.")
    return url


async def upload_result_file(result_path: Path, filename: str) -> str:
    upload_url = _build_result_upload_url()
    if not API_RESULT_UPLOAD_AUTHORIZATION:
        raise HTTPException(status_code=500, detail="api.result_upload_authorization is not configured.")

    try:
        async with httpx.AsyncClient(timeout=API_RESULT_UPLOAD_TIMEOUT_SECONDS) as client:
            with result_path.open("rb") as result_file:
                response = await client.post(
                    upload_url,
                    headers={"Authorization": API_RESULT_UPLOAD_AUTHORIZATION},
                    files={
                        "files": (
                            filename,
                            result_file,
                            DOCX_MEDIA_TYPE,
                        )
                    },
                )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ResultUploadError(
            f"Result file upload failed: {exc}",
            http_status=exc.response.status_code,
        ) from exc
    except httpx.HTTPError as exc:
        raise ResultUploadError(f"Result file upload failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ResultUploadError(
            "Result upload response was not valid JSON.",
            http_status=response.status_code,
        ) from exc

    try:
        return extract_uploaded_url(payload)
    except ResultUploadError as exc:
        exc.http_status = response.status_code
        raise
