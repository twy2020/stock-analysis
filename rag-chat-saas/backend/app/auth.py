from __future__ import annotations

import hmac
from datetime import UTC, datetime
from functools import wraps

from flask import current_app, g, jsonify, request

from app.extensions import database
from app.models import Session, token_digest


def error(code: str, message: str, status: int):
    return jsonify({"code": code, "message": message}), status


def load_session() -> None:
    g.current_user = None
    g.current_session = None
    token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if not token:
        return
    record = database.session.query(Session).filter_by(token_hash=token_digest(token)).one_or_none()
    if record is None or record.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC) or record.user.status != "ACTIVE":
        return
    g.current_session = record
    g.current_user = record.user


def authenticated(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            return error("AUTHENTICATION_REQUIRED", "Sign in required", 401)
        if g.current_user.password_change_required and request.endpoint not in {
            "auth.change_password", "auth.logout"
        }:
            return error("PASSWORD_CHANGE_REQUIRED", "Change the initial password", 428)
        return view(*args, **kwargs)
    return wrapped


def require_csrf() -> None:
    if (request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and g.current_session is not None and request.endpoint != "auth.login"):
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not hmac.compare_digest(token_digest(supplied), g.current_session.csrf_hash):
            from werkzeug.exceptions import Forbidden
            raise Forbidden("Invalid CSRF token")
