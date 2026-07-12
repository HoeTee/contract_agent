from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api_client_management import (
    ApiClientManagementError,
    create_api_client,
    load_api_clients,
    reset_api_client_secret,
    set_api_client_enabled,
    set_api_client_ips,
)


SECRET_NOTICE = "Store this secret securely. It is shown only once. If lost, reset it."


def print_secret(client_id: str, secret: str, *, reset: bool = False) -> None:
    action = "Reset secret for API client" if reset else "Created API client"
    print(f"{action}: {client_id}")
    print(f"Secret: {secret}")
    print(SECRET_NOTICE)


def create_client(args) -> None:
    try:
        client, secret = create_api_client(
            client_id=args.client_id,
            allowed_ips=args.allowed_ip,
        )
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))
    print_secret(client["client_id"], secret)


def reset_secret(args) -> None:
    try:
        client, secret = reset_api_client_secret(client_id=args.client_id)
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))
    print_secret(client["client_id"], secret, reset=True)


def list_clients(args) -> None:
    try:
        clients = load_api_clients()
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))

    if args.client_id:
        matches = [client for client in clients if client.get("client_id") == args.client_id]
        if not matches:
            raise SystemExit(f"API client not found: {args.client_id}")
        client = matches[0]
        print(f"client_id: {client.get('client_id', '')}")
        print(f"enabled: {str(bool(client.get('enabled', True))).lower()}")
        print("allowed_ips:")
        for ip in client.get("allowed_ips", []):
            print(f"  - {ip}")
        print(f"created_at: {client.get('created_at', '')}")
        print(f"secret_updated_at: {client.get('secret_updated_at', '')}")
        return

    print("client_id\tenabled\tallowed_ips")
    for client in clients:
        ips = ", ".join(client.get("allowed_ips", []))
        enabled = str(bool(client.get("enabled", True))).lower()
        print(f"{client.get('client_id', '')}\t{enabled}\t{ips}")


def set_ips(args) -> None:
    try:
        client = set_api_client_ips(
            client_id=args.client_id,
            allowed_ips=args.allowed_ip,
        )
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))
    print(f"Updated IP whitelist for API client: {client['client_id']}")


def disable_client(args) -> None:
    try:
        client = set_api_client_enabled(client_id=args.client_id, enabled=False)
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))
    print(f"Disabled API client: {client['client_id']}")


def enable_client(args) -> None:
    try:
        client = set_api_client_enabled(client_id=args.client_id, enabled=True)
    except ApiClientManagementError as exc:
        raise SystemExit(str(exc))
    print(f"Enabled API client: {client['client_id']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage API clients.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create an API client")
    create.add_argument("--client-id", required=True)
    create.add_argument("--allowed-ip", action="append", required=True)
    create.set_defaults(func=create_client)

    reset = subparsers.add_parser("reset-secret", help="Reset an API client secret")
    reset.add_argument("--client-id", required=True)
    reset.set_defaults(func=reset_secret)

    list_parser = subparsers.add_parser("list", help="List API clients")
    list_parser.add_argument("--client-id")
    list_parser.set_defaults(func=list_clients)

    set_ips_parser = subparsers.add_parser("set-ips", help="Replace an API client's IP whitelist")
    set_ips_parser.add_argument("--client-id", required=True)
    set_ips_parser.add_argument("--allowed-ip", action="append", required=True)
    set_ips_parser.set_defaults(func=set_ips)

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

