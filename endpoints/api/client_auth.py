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


def _header_secret_key(request: Request) -> str:
    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if authorization:
        return authorization
    return request.headers.get("x-api-key", "").strip()


def _extract_secret_key(request: Request, fields: dict[str, Any]) -> str:
    return (
        _header_secret_key(request)
        or str(fields.get("secret_key") or "").strip()
        or str(request.query_params.get("secret_key") or "").strip()
    )


async def resolve_api_client(
    request: Request,
    payload: dict[str, Any] | None = None,
) -> ApiClient:
    fields = await _body_fields(request, payload)
    secret_key = _extract_secret_key(request, fields)
    if not secret_key:
        raise HTTPException(status_code=401, detail="secret_key is required.")

    try:
        clients = load_api_clients()
    except ApiClientAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    matches = [
        client
        for client in clients
        if client.get("enabled", True) and verify_password(secret_key, str(client.get("secret_hash", "")))
    ]
    if not matches:
        raise HTTPException(status_code=401, detail="Invalid API client credentials.")
    if len(matches) > 1:
        raise HTTPException(status_code=500, detail="API client secret matches multiple clients.")

    client = matches[0]
    client_id = str(client.get("client_id") or "").strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="API client record is missing client_id.")
    source_ip = _request_source_ip(request)
    return ApiClient(
        client_id=client_id,
        client_dir=str(client.get("client_dir") or client_dir_name(client_id)),
        source_ip=source_ip,
    )
