from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from endpoints.runtime.auth import hash_password, verify_password


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_CLIENTS_FILE = PROJECT_ROOT / "user_profiles" / "api_clients.json"
SECRET_PREFIX = "api_"
SECRET_TOKEN_BYTES = 32


class ApiClientManagementError(Exception):
    pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(SECRET_TOKEN_BYTES)


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
        raise ApiClientManagementError("api_clients.json must contain a clients list.")
    return clients


def save_api_clients(
    clients: list[dict[str, Any]],
    clients_file: str | Path = API_CLIENTS_FILE,
) -> None:
    path = Path(clients_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"clients": clients}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_client_index(clients: list[dict[str, Any]], client_id: str) -> int | None:
    for index, client in enumerate(clients):
        if client.get("client_id") == client_id:
            return index
    return None


def normalize_allowed_ips(allowed_ips: list[str]) -> list[str]:
    result: list[str] = []
    for ip in allowed_ips:
        value = str(ip).strip()
        if value and value not in result:
            result.append(value)
    return result


def create_api_client(
    *,
    client_id: str,
    allowed_ips: list[str],
    clients_file: str | Path = API_CLIENTS_FILE,
) -> tuple[dict[str, Any], str]:
    client_id = client_id.strip()
    if not client_id:
        raise ApiClientManagementError("client_id is required.")
    normalized_ips = normalize_allowed_ips(allowed_ips)
    if not normalized_ips:
        raise ApiClientManagementError("At least one allowed IP is required.")

    clients = load_api_clients(clients_file)
    if find_client_index(clients, client_id) is not None:
        raise ApiClientManagementError(f"API client already exists: {client_id}")

    secret = generate_secret()
    timestamp = now_text()
    client = {
        "client_id": client_id,
        "client_dir": client_dir_name(client_id),
        "secret_hash": hash_password(secret),
        "allowed_ips": normalized_ips,
        "enabled": True,
        "created_at": timestamp,
        "secret_updated_at": timestamp,
    }
    clients.append(client)
    save_api_clients(clients, clients_file)
    return client, secret


def reset_api_client_secret(
    *,
    client_id: str,
    clients_file: str | Path = API_CLIENTS_FILE,
) -> tuple[dict[str, Any], str]:
    clients = load_api_clients(clients_file)
    index = find_client_index(clients, client_id)
    if index is None:
        raise ApiClientManagementError(f"API client not found: {client_id}")

    secret = generate_secret()
    clients[index]["secret_hash"] = hash_password(secret)
    clients[index]["secret_updated_at"] = now_text()
    clients[index]["client_dir"] = clients[index].get("client_dir") or client_dir_name(client_id)
    save_api_clients(clients, clients_file)
    return clients[index], secret


def set_api_client_ips(
    *,
    client_id: str,
    allowed_ips: list[str],
    clients_file: str | Path = API_CLIENTS_FILE,
) -> dict[str, Any]:
    normalized_ips = normalize_allowed_ips(allowed_ips)
    if not normalized_ips:
        raise ApiClientManagementError("At least one allowed IP is required.")

    clients = load_api_clients(clients_file)
    index = find_client_index(clients, client_id)
    if index is None:
        raise ApiClientManagementError(f"API client not found: {client_id}")
    clients[index]["allowed_ips"] = normalized_ips
    clients[index]["ips_updated_at"] = now_text()
    clients[index]["client_dir"] = clients[index].get("client_dir") or client_dir_name(client_id)
    save_api_clients(clients, clients_file)
    return clients[index]


def set_api_client_enabled(
    *,
    client_id: str,
    enabled: bool,
    clients_file: str | Path = API_CLIENTS_FILE,
) -> dict[str, Any]:
    clients = load_api_clients(clients_file)
    index = find_client_index(clients, client_id)
    if index is None:
        raise ApiClientManagementError(f"API client not found: {client_id}")
    clients[index]["enabled"] = enabled
    clients[index]["enabled_updated_at"] = now_text()
    clients[index]["client_dir"] = clients[index].get("client_dir") or client_dir_name(client_id)
    save_api_clients(clients, clients_file)
    return clients[index]


def verify_api_client_secret(client: dict[str, Any], secret_key: str) -> bool:
    return verify_password(secret_key, str(client.get("secret_hash", "")))
