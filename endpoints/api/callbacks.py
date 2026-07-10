from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import HTTPException

from config import (
    API_CALLBACK_ENABLED,
    API_CALLBACK_FILE_FIELD,
    API_CALLBACK_URL,
)
from endpoints.runtime.document_validation import DOCX_MEDIA_TYPE


async def post_api_review_callback(
    *,
    output_path: Path,
    response_filename: str,
    meta_fields: dict[str, str],
) -> None:
    if not API_CALLBACK_ENABLED:
        return

    if not API_CALLBACK_URL:
        raise HTTPException(
            status_code=500,
            detail="API_CALLBACK_ENABLED=True 时必须配置 API_CALLBACK_URL。",
        )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with output_path.open("rb") as report_file:
                response = await client.post(
                    API_CALLBACK_URL,
                    data=meta_fields,
                    files={
                        API_CALLBACK_FILE_FIELD: (
                            response_filename,
                            report_file,
                            DOCX_MEDIA_TYPE,
                        )
                    },
                )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"批注文件回调发送失败：{exc}",
        ) from exc
