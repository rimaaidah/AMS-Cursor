from __future__ import annotations

import time
from typing import Any

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import load_db, next_id, save_db


def ensure_seed() -> None:
    db = load_db()
    users: list[dict[str, Any]] = db.get("users", [])
    if any(u.get("role") == "admin" for u in users):
        return

    users.append(
        {
            "id": next_id(users),
            "username": "admin",
            "password_hash": generate_password_hash("admin"),
            "role": "admin",
            "ref": {"type": "admin", "id": 1},
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
    )
    db["users"] = users
    save_db(db)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    db = load_db()
    for u in db.get("users", []):
        if u.get("username") == username and check_password_hash(
            u.get("password_hash", ""), password
        ):
            return u
    return None


def login_user(user: dict[str, Any]) -> None:
    session["user_id"] = user["id"]


def logout_user() -> None:
    session.pop("user_id", None)


def current_user() -> dict[str, Any] | None:
    uid = session.get("user_id")
    if not uid:
        return None
    db = load_db()
    return next((u for u in db.get("users", []) if u.get("id") == uid), None)


def change_credentials(
    user_id: int, *, new_username: str | None = None, new_password: str | None = None
) -> tuple[bool, str]:
    db = load_db()
    users: list[dict[str, Any]] = db.get("users", [])
    u = next((x for x in users if x.get("id") == user_id), None)
    if not u:
        return False, "User tidak ditemukan."

    if new_username:
        if any(x.get("username") == new_username and x.get("id") != user_id for x in users):
            return False, "Username sudah dipakai."
        u["username"] = new_username

    if new_password:
        if len(new_password) < 4:
            return False, "Password minimal 4 karakter."
        u["password_hash"] = generate_password_hash(new_password)

    u["updated_at"] = int(time.time())
    save_db(db)
    return True, "Profil berhasil diperbarui."

