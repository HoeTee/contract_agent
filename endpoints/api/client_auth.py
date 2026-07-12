from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from fastapi import HTTPException, Request

from services.api_client_management import (
    ApiClientManagementError,
    client_dir_name,
    load_api_clients,
    verify_api_client_secret,
)


@dataclass(frozen=True)
class ApiClient:
    client_id: str
    client_dir: str
    source_ip: str


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
    except ApiClientManagementError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    client = next((item for item in clients if item.get("client_id") == client_id), None)
    if client is None or not client.get("enabled", True):
        raise HTTPException(status_code=401, detail="Invalid API client credentials.")

    if not verify_api_client_secret(client, secret_key):
        raise HTTPException(status_code=401, detail="Invalid API client credentials.")

    source_ip = _request_source_ip(request)
    allowed_ips = [str(ip).strip() for ip in client.get("allowed_ips", []) if str(ip).strip()]
    if allowed_ips and source_ip not in allowed_ips:
        raise HTTPException(status_code=403, detail="Source IP is not allowed for this API client.")

    return ApiClient(
        client_id=client_id,
        client_dir=str(client.get("client_dir") or client_dir_name(client_id)),
        source_ip=source_ip,
    )
