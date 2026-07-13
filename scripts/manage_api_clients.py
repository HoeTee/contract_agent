from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from endpoints.runtime.auth import hash_password


API_CLIENTS_FILE = PROJECT_ROOT / "user_profiles" / "api_clients.json"


class ApiClientCliError(Exception):
    pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        raise ApiClientCliError("api_clients.json must contain a clients list.")
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


def register_api_client(
    *,
    client_id: str,
    secret_key: str,
    clients_file: str | Path = API_CLIENTS_FILE,
) -> dict[str, Any]:
    client_id = client_id.strip()
    secret_key = secret_key.strip()
    if not client_id:
        raise ApiClientCliError("client_id is required.")
    if not secret_key:
        raise ApiClientCliError("secret_key is required.")

    clients = load_api_clients(clients_file)
    if find_client_index(clients, client_id) is not None:
        raise ApiClientCliError(f"API client already exists: {client_id}")

    timestamp = now_text()
    client = {
        "client_id": client_id,
        "client_dir": client_dir_name(client_id),
        "secret_hash": hash_password(secret_key),
        "enabled": True,
        "created_at": timestamp,
        "secret_updated_at": timestamp,
    }
    clients.append(client)
    save_api_clients(clients, clients_file)
    return client


def reset_api_client_secret(
    *,
    client_id: str,
    secret_key: str,
    clients_file: str | Path = API_CLIENTS_FILE,
) -> dict[str, Any]:
    secret_key = secret_key.strip()
    if not secret_key:
        raise ApiClientCliError("secret_key is required.")

    clients = load_api_clients(clients_file)
    index = find_client_index(clients, client_id)
    if index is None:
        raise ApiClientCliError(f"API client not found: {client_id}")

    clients[index]["secret_hash"] = hash_password(secret_key)
    clients[index]["secret_updated_at"] = now_text()
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
        raise ApiClientCliError(f"API client not found: {client_id}")
    clients[index]["enabled"] = enabled
    clients[index]["enabled_updated_at"] = now_text()
    clients[index]["client_dir"] = clients[index].get("client_dir") or client_dir_name(client_id)
    save_api_clients(clients, clients_file)
    return clients[index]


def register_client(args) -> None:
    try:
        client = register_api_client(client_id=args.client_id, secret_key=args.secret_key)
    except ApiClientCliError as exc:
        raise SystemExit(str(exc))
    print(f"Registered API client: {client['client_id']}")


def reset_secret(args) -> None:
    try:
        client = reset_api_client_secret(client_id=args.client_id, secret_key=args.secret_key)
    except ApiClientCliError as exc:
        raise SystemExit(str(exc))
    print(f"Reset secret for API client: {client['client_id']}")


def list_clients(args) -> None:
    try:
        clients = load_api_clients()
    except ApiClientCliError as exc:
        raise SystemExit(str(exc))

    if args.client_id:
        matches = [client for client in clients if client.get("client_id") == args.client_id]
        if not matches:
            raise SystemExit(f"API client not found: {args.client_id}")
        client = matches[0]
        print(f"client_id: {client.get('client_id', '')}")
        print(f"client_dir: {client.get('client_dir', '')}")
        print(f"enabled: {str(bool(client.get('enabled', True))).lower()}")
        print(f"created_at: {client.get('created_at', '')}")
        print(f"secret_updated_at: {client.get('secret_updated_at', '')}")
        return

    print("client_id\tenabled\tclient_dir\tcreated_at\tsecret_updated_at")
    for client in clients:
        enabled = str(bool(client.get("enabled", True))).lower()
        print(
            f"{client.get('client_id', '')}\t"
            f"{enabled}\t"
            f"{client.get('client_dir', '')}\t"
            f"{client.get('created_at', '')}\t"
            f"{client.get('secret_updated_at', '')}"
        )


def disable_client(args) -> None:
    try:
        client = set_api_client_enabled(client_id=args.client_id, enabled=False)
    except ApiClientCliError as exc:
        raise SystemExit(str(exc))
    print(f"Disabled API client: {client['client_id']}")


def enable_client(args) -> None:
    try:
        client = set_api_client_enabled(client_id=args.client_id, enabled=True)
    except ApiClientCliError as exc:
        raise SystemExit(str(exc))
    print(f"Enabled API client: {client['client_id']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage API clients.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register", help="Register an API client with a platform secret")
    register.add_argument("--client-id", required=True)
    register.add_argument("--secret-key", required=True)
    register.set_defaults(func=register_client)

    reset = subparsers.add_parser("reset-secret", help="Replace an API client secret")
    reset.add_argument("--client-id", required=True)
    reset.add_argument("--secret-key", required=True)
    reset.set_defaults(func=reset_secret)

    list_parser = subparsers.add_parser("list", help="List API clients")
    list_parser.add_argument("--client-id")
    list_parser.set_defaults(func=list_clients)

    disable = subparsers.add_parser("disable", help="Disable an API client")
    disable.add_argument("--client-id", required=True)
    disable.set_defaults(func=disable_client)

    enable = subparsers.add_parser("enable", help="Enable an API client")
    enable.add_argument("--client-id", required=True)
    enable.set_defaults(func=enable_client)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
