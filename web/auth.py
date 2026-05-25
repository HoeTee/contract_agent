from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def load_users(users_file: str | Path) -> list[dict[str, Any]]:
    path = Path(users_file)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    users = data.get("users", [])
    if not isinstance(users, list):
        raise ValueError("users.json must contain a users list.")
    return users


def save_users(users_file: str | Path, users: list[dict[str, Any]]) -> None:
    path = Path(users_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"users": users}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def find_user(users_file: str | Path, username: str) -> dict[str, Any] | None:
    for user in load_users(users_file):
        if user.get("username") == username:
            return user
    return None


def verify_login(users_file: str | Path, username: str, password: str) -> dict[str, Any] | None:
    user = find_user(users_file, username)
    if not user or not user.get("enabled", True):
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return user


def require_username(request) -> str | None:
    return request.session.get("username")
