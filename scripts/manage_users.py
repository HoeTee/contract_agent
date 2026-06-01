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
from loggers.resolve_review_task_paths import initialize_user_data_dir, safe_path_part
from web.auth import hash_password, load_users, save_users


def find_index(users: list[dict], username: str) -> int | None:
    for index, user in enumerate(users): # enumerate to find repetition
        if user.get("username") == username:
            return index
    return None


def create_user(args) -> None:
    username = safe_path_part(args.username, "user")
    users = load_users(USERS_FILE) # [] if no users.json exists
    if find_index(users, username) is not None:
        raise SystemExit(f"用户已存在：{username}")

    users.append({
        "username": username,
        "password_hash": hash_password(args.password),
        "display_name": args.display_name or username,
        "enabled": True,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_users(USERS_FILE, users) # update users.json
    initialize_user_data_dir(Path(DATA_DIR), username) # create user data dir right afterward
    print(f"Created user: {username}")


def reset_password(args) -> None:
    users = load_users(USERS_FILE)
    index = find_index(users, args.username)
    if index is None:
        raise SystemExit(f"未找到用户：{args.username}")
    users[index]["password_hash"] = hash_password(args.password)
    users[index]["password_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(USERS_FILE, users)
    print(f"Password reset for user: {args.username}")


def disable_user(args) -> None:
    users = load_users(USERS_FILE)
    index = find_index(users, args.username)
    if index is None:
        raise SystemExit(f"未找到用户：{args.username}")
    users[index]["enabled"] = False
    users[index]["disabled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(USERS_FILE, users)
    print(f"Disabled user: {args.username}")


def enable_user(args) -> None:
    users = load_users(USERS_FILE)
    index = find_index(users, args.username)
    if index is None:
        raise SystemExit(f"未找到用户：{args.username}")
    users[index]["enabled"] = True
    users[index]["enabled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_users(USERS_FILE, users)
    initialize_user_data_dir(Path(DATA_DIR), args.username)
    print(f"Enabled user: {args.username}")


def delete_user(args) -> None:
    username = safe_path_part(args.username, "user")
    users = load_users(USERS_FILE)
    index = find_index(users, username)
    if index is None:
        raise SystemExit(f"未找到用户：{username}")

    del users[index]
    save_users(USERS_FILE, users)
    print(f"Deleted user account: {username}")

    if args.keep_data:
        print(f"Kept user data directory: {Path(DATA_DIR) / username}")
        return

    data_root = Path(DATA_DIR).resolve()
    user_root = (data_root / username).resolve()
    if data_root == user_root or data_root not in user_root.parents:
        raise SystemExit(f"拒绝删除不安全路径：{user_root}")

    if user_root.exists():
        shutil.rmtree(user_root)
        print(f"Deleted user data directory: {user_root}")
    else:
        print(f"未找到用户数据目录：{user_root}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage web users.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a user")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--display-name", default="")
    create.set_defaults(func=create_user)

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
