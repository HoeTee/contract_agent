from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DATA_DIR, USERS_FILE
from endpoints.runtime.auth import VALID_ROLES, hash_password, load_users, save_users
from loggers.resolve_review_task_paths import initialize_user_data_dir, safe_path_part


class UserManagementError(Exception):
    pass


def find_user_index(users: list[dict], username: str) -> int | None:
    for index, user in enumerate(users):
        if user.get("username") == username:
            return index
    return None


def validate_role(role: str) -> str:
    normalized = (role or "").strip().lower()
    if normalized not in VALID_ROLES:
        raise UserManagementError(f"Role must be user or admin: {role}")
    return normalized


def create_user_account(
    *,
    username: str,
    password: str,
    display_name: str = "",
    role: str = "user",
    users_file: str | Path = USERS_FILE,
    data_dir: str | Path = DATA_DIR,
) -> str:
    safe_username = safe_path_part(username, "user")
    normalized_role = validate_role(role)
    users = load_users(users_file)
    if find_user_index(users, safe_username) is not None:
        raise UserManagementError(f"User already exists: {safe_username}")

    users.append({
        "username": safe_username,
        "password_hash": hash_password(password),
        "display_name": display_name or safe_username,
        "role": normalized_role,
        "enabled": True,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_users(users_file, users)
    initialize_user_data_dir(Path(data_dir), safe_username)
    return safe_username


def set_user_role(
    *,
    username: str,
    role: str,
    users_file: str | Path = USERS_FILE,
) -> str:
    normalized_role = validate_role(role)
    users = load_users(users_file)
    index = find_user_index(users, username)
    if index is None:
        raise UserManagementError(f"User not found: {username}")
    users[index]["role"] = normalized_role
    users[index]["role_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(users_file, users)
    return normalized_role


def reset_user_password(
    *,
    username: str,
    password: str,
    users_file: str | Path = USERS_FILE,
) -> None:
    users = load_users(users_file)
    index = find_user_index(users, username)
    if index is None:
        raise UserManagementError(f"User not found: {username}")
    users[index]["password_hash"] = hash_password(password)
    users[index]["password_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(users_file, users)


def set_user_enabled(
    *,
    username: str,
    enabled: bool,
    users_file: str | Path = USERS_FILE,
    data_dir: str | Path = DATA_DIR,
) -> None:
    users = load_users(users_file)
    index = find_user_index(users, username)
    if index is None:
        raise UserManagementError(f"User not found: {username}")
    users[index]["enabled"] = enabled
    key = "enabled_at" if enabled else "disabled_at"
    users[index][key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(users_file, users)
    if enabled:
        initialize_user_data_dir(Path(data_dir), username)


def delete_user_account(
    *,
    username: str,
    keep_data: bool = False,
    users_file: str | Path = USERS_FILE,
    data_dir: str | Path = DATA_DIR,
) -> Path | None:
    safe_username = safe_path_part(username, "user")
    users = load_users(users_file)
    index = find_user_index(users, safe_username)
    if index is None:
        raise UserManagementError(f"User not found: {safe_username}")

    del users[index]
    save_users(users_file, users)

    user_root = Path(data_dir) / safe_username
    if keep_data:
        return user_root

    data_root = Path(data_dir).resolve()
    resolved_user_root = user_root.resolve()
    if data_root == resolved_user_root or data_root not in resolved_user_root.parents:
        raise UserManagementError(f"Refusing to delete unsafe path: {resolved_user_root}")

    if resolved_user_root.exists():
        shutil.rmtree(resolved_user_root)
        return resolved_user_root
    return None


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
