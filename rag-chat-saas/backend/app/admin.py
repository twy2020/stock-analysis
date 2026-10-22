from __future__ import annotations

from functools import wraps

from flask import g

from app.auth import authenticated, error


def administrator(view):
    @wraps(view)
    @authenticated
    def wrapped(*args, **kwargs):
        if g.current_user.role != "ADMIN":
            return error("ACCESS_DENIED", "Administrator access required", 403)
        return view(*args, **kwargs)
    return wrapped
