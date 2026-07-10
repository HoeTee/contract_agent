from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from endpoints.runtime.auth import VALID_ROLES
from services.user_management import (
    UserManagementError,
    create_user_account,
    delete_user_account,
    reset_user_password,
    set_user_enabled,
    set_user_role,
)


def create_user(args) -> None:
    try:
        username = create_user_account(
            username=args.username,
            password=args.password,
            display_name=args.display_name,
            role=args.role,
        )
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已创建用户：{username}")


def set_role(args) -> None:
    try:
        role = set_user_role(username=args.username, role=args.role)
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已更新用户角色：{args.username} -> {role}")


def reset_password(args) -> None:
    try:
        reset_user_password(username=args.username, password=args.password)
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已重置用户密码：{args.username}")


def disable_user(args) -> None:
    try:
        set_user_enabled(username=args.username, enabled=False)
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已禁用用户：{args.username}")


def enable_user(args) -> None:
    try:
        set_user_enabled(username=args.username, enabled=True)
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已启用用户：{args.username}")


def delete_user(args) -> None:
    try:
        data_path = delete_user_account(username=args.username, keep_data=args.keep_data)
    except UserManagementError as exc:
        raise SystemExit(str(exc))
    print(f"已删除用户账号：{args.username}")
    if args.keep_data:
        print(f"已保留用户数据目录：{data_path}")
    elif data_path:
        print(f"已删除用户数据目录：{data_path}")
    else:
        print("未找到用户数据目录。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage web users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a user")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--display-name", default="")
    create.add_argument("--role", choices=sorted(VALID_ROLES), default="user")
    create.set_defaults(func=create_user)

    role = subparsers.add_parser("set-role", help="Set a user's role")
    role.add_argument("--username", required=True)
    role.add_argument("--role", choices=sorted(VALID_ROLES), required=True)
    role.set_defaults(func=set_role)

    reset = subparsers.add_parser("reset-password", help="Reset a user's password")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password", required=True)
    reset.set_defaults(func=reset_password)

    disable = subparsers.add_parser("disable", help="Disable a user")
    disable.add_argument("--username", required=True)
    disable.set_defaults(func=disable_user)

    enable = subparsers.add_parser("enable", help="Enable a user")
    enable.add_argument("--username", required=True)
    enable.set_defaults(func=enable_user)

    delete = subparsers.add_parser("delete", help="Delete a user")
    delete.add_argument("--username", required=True)
    delete.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep data/<username> instead of deleting it.",
    )
    delete.set_defaults(func=delete_user)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
