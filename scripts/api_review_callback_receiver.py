from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile as StarletteUploadFile


app = FastAPI(
    title="API Review Callback Receiver",
    description="Local test receiver for POST /oa/review callback requests.",
)

MAX_IN_MEMORY_RECORDS = 20
READ_CHUNK_SIZE = 1024 * 1024
_received_callbacks: list[dict[str, Any]] = []


def _now_beijing_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


async def _read_upload_size(upload: StarletteUploadFile) -> int:
    total_size = 0
    while True:
        chunk = await upload.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
    return total_size


def _remember_callback(record: dict[str, Any]) -> None:
    _received_callbacks.append(record)
    del _received_callbacks[:-MAX_IN_MEMORY_RECORDS]


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "stored_records": len(_received_callbacks),
        "binary_files_persisted": False,
    }


@app.get("/last")
async def last_callbacks() -> dict[str, Any]:
    return {
        "records": _received_callbacks,
        "binary_files_persisted": False,
    }


@app.post("/callback")
async def receive_callback(request: Request) -> dict[str, Any]:
    form = await request.form()
    text_fields: dict[str, list[str]] = {}
    file_fields: list[dict[str, Any]] = []

    for field_name, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            file_fields.append(
                {
                    "field_name": field_name,
                    "filename": value.filename,
                    "content_type": value.content_type,
                    "size_bytes": await _read_upload_size(value),
                    "persisted": False,
                }
            )
        else:
            text_fields.setdefault(field_name, []).append(str(value))

    record = {
        "ok": True,
        "request_id": uuid.uuid4().hex[:12],
        "received_at": _now_beijing_iso(),
        "text_fields": text_fields,
        "file_fields": file_fields,
        "binary_files_persisted": False,
    }
    _remember_callback(record)
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    return record
