from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable, TypeVar

from flask import flash, redirect, request, url_for

from .auth import current_user

F = TypeVar("F", bound=Callable[..., object])


def login_required(view: F) -> F:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def role_required(roles: Iterable[str]):
    roles_set = set(roles)

    def deco(view: F) -> F:
        @wraps(view)
        def wrapper(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for("login", next=request.path))
            if roles_set and u.get("role") not in roles_set:
                flash("Akses ditolak.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return deco

