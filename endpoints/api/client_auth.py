from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from typing import Any

from fastapi import HTTPException, Request

from endpoints.runtime.auth import verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_CLIENTS_FILE = PROJECT_ROOT / "user_profiles" / "api_clients.json"


@dataclass(frozen=True)
class ApiClient:
    client_id: str
    client_dir: str
    source_ip: str


class ApiClientAuthError(Exception):
    pass


def client_dir_name(client_id: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", client_id).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "api_client"


def load_api_clients(clients_file: str | Path = API_CLIENTS_FILE) -> list[dict[str, Any]]:
    path = Path(clients_file)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    clients = data.get("clients", [])
    if not isinstance(clients, list):
        raise ApiClientAuthError("api_clients.json must contain a clients list.")
    return clients


def _request_source_ip(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host or ""


async def _body_fields(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            data = {}
        return data if isinstance(data, dict) else {}
    form = await request.form()
    return dict(form)


async def resolve_api_client(
    request: Request,
    payload: dict[str, Any] | None = None,
) -> ApiClient:
    fields = await _body_fields(request, payload)
    client_id = str(fields.get("client_id") or "").strip()
    secret_key = str(fields.get("secret_key") or "").strip()
    if not client_id or not secret_key:
        raise HTTPException(status_code=401, detail="client_id and secret_key are required.")

    try:
        clients = load_api_clients()
    except ApiClientAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    client = next((item for item in clients if item.get("client_id") == client_id), None)
    if client is None or not client.get("enabled", True):
        raise HTTPException(status_code=401, detail="Invalid API client credentials.")

    if not verify_password(secret_key, str(client.get("secret_hash", ""))):
        raise HTTPException(status_code=401, detail="Invalid API client credentials.")

    source_ip = _request_source_ip(request)
    return ApiClient(
        client_id=client_id,
        client_dir=str(client.get("client_dir") or client_dir_name(client_id)),
        source_ip=source_ip,
    )
