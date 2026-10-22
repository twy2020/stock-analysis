from __future__ import annotations

import secrets
import hmac
import re
from sqlalchemy.exc import IntegrityError
from app import registration

from flask import Blueprint, current_app, g, jsonify, request

from app.auth import authenticated, error
from app.extensions import database
from app.models import Session, User, now, password_hasher, token_digest


blueprint = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def user_json(user: User) -> dict:
    return {"username": user.username, "role": user.role,
            "passwordChangeRequired": user.password_change_required}


def session_response(user: User, token: str, csrf: str):
    response = jsonify({"user": user_json(user), "csrfToken": csrf})
    response.set_cookie(current_app.config["SESSION_COOKIE_NAME"], token, httponly=True,
                        secure=current_app.config["SESSION_SECURE"], samesite="Lax",
                        max_age=current_app.config["SESSION_TTL_SECONDS"], path="/")
    return response


@blueprint.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", ""))
    user = database.session.query(User).filter_by(username=username, status="ACTIVE").one_or_none()
    if user is None or not user.verify_password(password):
        return error("INVALID_CREDENTIALS", "Username or password is incorrect", 401)
    record, token, csrf = Session.issue(user, current_app.config["SESSION_TTL_SECONDS"])
    user.last_login_at = now()
    database.session.add(record)
    database.session.commit()
    return session_response(user, token, csrf)


@blueprint.get('/registration')
def registration_options():
    return jsonify(inviteRequired=bool(registration.settings().get('inviteRequired')))


@blueprint.post('/register')
def register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get('username', '')).strip().lower()
    password = payload.get('password', '')
    if not re.fullmatch(r'[\w.@+-]{3,80}', username):
        return error('INVALID_USERNAME', '账号需为 3–80 位文字、数字或 . @ + - _，不能包含空格', 400)
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        return error('INVALID_PASSWORD', '密码需为 12–256 个字符', 400)
    policy = registration.settings()
    supplied = str(payload.get('inviteCode', '')).strip()
    expected = policy.get('inviteCode', '')
    if policy.get('inviteRequired') and (not expected or not hmac.compare_digest(token_digest(supplied), token_digest(expected))):
        return error('INVALID_INVITE_CODE', '邀请码不正确，请向管理员获取当前邀请码', 400)
    if database.session.query(User).filter_by(username=username).first():
        return error('USERNAME_TAKEN', '该账号已注册，请更换账号或直接登录', 409)
    user = User.create(username, password, role='USER', password_change_required=False)
    database.session.add(user)
    try:
        database.session.flush()
        record, token, csrf = Session.issue(user, current_app.config['SESSION_TTL_SECONDS'])
        database.session.add(record)
        user.last_login_at = now()
        database.session.commit()
    except IntegrityError:
        database.session.rollback()
        return error('USERNAME_TAKEN', '该账号已注册，请更换账号或直接登录', 409)
    g.current_user = user
    response = session_response(user, token, csrf)
    response.status_code = 201
    return response


@blueprint.get("/session")
def current_session():
    if g.current_user is None:
        return error("AUTHENTICATION_REQUIRED", "Sign in required", 401)
    csrf = secrets.token_urlsafe(32)
    g.current_session.csrf_hash = token_digest(csrf)
    database.session.commit()
    return jsonify({"user": user_json(g.current_user), "csrfToken": csrf})


@blueprint.post("/change-password")
@authenticated
def change_password():
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    if len(password) < 12:
        return error("INVALID_PASSWORD", "Password must be at least 12 characters", 400)
    user = g.current_user
    user.password_hash = password_hasher.hash(password)
    user.password_change_required = False
    database.session.query(Session).filter(Session.user_id == user.id).delete()
    record, token, csrf = Session.issue(user, current_app.config["SESSION_TTL_SECONDS"])
    database.session.add(record)
    database.session.commit()
    return session_response(user, token, csrf)


@blueprint.post("/logout")
@authenticated
def logout():
    database.session.delete(g.current_session)
    database.session.commit()
    response = current_app.response_class(status=204)
    response.delete_cookie(current_app.config["SESSION_COOKIE_NAME"], path="/")
    return response
