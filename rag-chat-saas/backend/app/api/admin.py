from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from app.admin import administrator
from app.auth import error
from app.crypto import cipher, decrypt_json, encrypt_json, encrypt_secret
from app.extensions import database
from app.models import AiAccount, AiProvider, ProviderRequest, RagRequest, SystemSetting, User
from app.model_catalog import discover_models, normalized_price


blueprint = Blueprint("admin", __name__, url_prefix="/api/v1/admin")
PROVIDER_TYPES = {"SILICONFLOW", "DEEPSEEK", "OPENAI", "OPENAI_COMPATIBLE"}


@blueprint.get('/settings/model')
@administrator
def get_model_settings():
    from app.core_client import enabled,CoreClient,CoreError
    if not enabled():return jsonify({'backend':'local'})
    try:return jsonify({'backend':'core',**CoreClient().request('GET','/v1/settings/model')})
    except CoreError as exc:return error(exc.code,'无法读取 Core 模型设置',503)


@blueprint.put('/settings/model')
@administrator
def put_model_settings():
    from app.core_client import enabled,CoreClient,CoreError
    if not enabled():return error('CORE_NOT_CONFIGURED','当前未使用 Core',400)
    value=request.get_json(silent=True)
    if not isinstance(value,dict) or set(value)!={'revision','modelProfile'}:
        return error('INVALID_REQUEST','请选择 Core 授权的模型',400)
    try:return jsonify({'backend':'core',**CoreClient().request('PUT','/v1/settings/model',value)})
    except CoreError as exc:
        messages={'ACTIVE_RUNS_CONFIGURATION_LOCKED':'有对话正在执行，请完成后再切换模型',
                  'CONFIGURATION_CONFLICT':'Core 配置已更新，请刷新后重试','MODEL_FORBIDDEN':'该模型未授权给股票服务',
                  'MODEL_TOOLS_REQUIRED':'该模型不支持工具调用','CONFIGURATION_READ_ONLY':'Core 配置为只读'}
        return error(exc.code,messages.get(exc.code,'无法保存 Core 模型设置'),409 if exc.code in messages else 503)


@blueprint.get('/settings/web-proxy')
@administrator
def get_web_proxy():
    from app.web_proxy import settings,view
    return jsonify(view(settings()))


@blueprint.get('/settings/search-engines')
@administrator
def get_search_engines():
    from app.search_manager import settings,view
    return jsonify(view(settings()))


@blueprint.put('/settings/search-engines')
@administrator
def put_search_engines():
    from app.search_manager import settings,view,validate,save
    try:value=validate(request.get_json(silent=True),settings())
    except ValueError as exc:return error('INVALID_REQUEST',str(exc),400)
    save(value)
    return jsonify(view(value))


@blueprint.post('/settings/search-engines/<provider>/test')
@administrator
def test_search_engine(provider):
    from pathlib import Path
    from flask import current_app
    from app.search_manager import settings,test_provider
    from app.web_proxy import settings as proxy_settings
    try:return jsonify(test_provider(provider,settings(),proxy_settings(),str(Path(current_app.config['DATABASE_PATH']).parent/'stock-web')))
    except ValueError as exc:return error('INVALID_REQUEST',str(exc),400)


@blueprint.put('/settings/web-proxy')
@administrator
def put_web_proxy():
    from app.web_proxy import settings,view,validate,save
    try:value=validate(request.get_json(silent=True),settings())
    except ValueError as exc:return error('INVALID_REQUEST',str(exc),400)
    save(value)
    return jsonify(view(value))


@blueprint.post('/settings/web-proxy/test')
@administrator
def test_web_proxy():
    from app.web_proxy import settings,transport_url
    value=settings()
    if not value['url']:return error('PROXY_NOT_CONFIGURED','请先保存代理地址',400)
    started=time.monotonic()
    try:
        with httpx.Client(proxy=transport_url(value['url']),timeout=6,trust_env=False,follow_redirects=False) as client:
            with client.stream('GET','https://example.com') as response:
                return jsonify(ok=response.status_code==200,status=response.status_code,elapsedMs=int((time.monotonic()-started)*1000))
    except Exception:return jsonify(ok=False,code='WEB_PROXY_UNAVAILABLE',elapsedMs=int((time.monotonic()-started)*1000))


@blueprint.get('/settings/features')
@administrator
def get_feature_settings():
    from app.features import settings
    return jsonify(settings())


@blueprint.put('/settings/features')
@administrator
def put_feature_settings():
    from app.features import save, private_settings, settings
    payload = request.get_json(silent=True) or {}
    value = private_settings()
    if set(payload)-{'ragEnabled','webEnabled'}:
        return error('INVALID_REQUEST', '未知功能设置', 400)
    if any(type(payload[k]) is not bool for k in ('ragEnabled','webEnabled') if k in payload):
        return error('INVALID_REQUEST', '请选择是否开放知识库检索', 400)
    value.update(payload)
    save(value)
    return jsonify(settings())


@blueprint.get('/settings/registration')
@administrator
def get_registration_settings():
    from app import registration
    return jsonify(registration.view(registration.settings()))


@blueprint.put('/settings/registration')
@administrator
def put_registration_settings():
    from app import registration
    payload = request.get_json(silent=True) or {}
    required = payload.get('inviteRequired')
    if not isinstance(required, bool):
        return error('INVALID_REQUEST', '请选择是否需要邀请码', 400)
    value = registration.settings()
    code = payload.get('inviteCode', '')
    if not isinstance(code, str):
        return error('INVALID_REQUEST', '邀请码格式不正确', 400)
    code = code.strip()
    if code and not 6 <= len(code) <= 128:
        return error('INVALID_REQUEST', '邀请码需为 6–128 个字符', 400)
    if code:
        value['inviteCode'] = code
    if required and not value.get('inviteCode'):
        return error('INVALID_REQUEST', '请先设置系统邀请码', 400)
    value['inviteRequired'] = required
    registration.save(value)
    return jsonify(registration.view(value))


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def rag_view(value: dict) -> dict:
    return {"baseUrl": value.get("baseUrl", ""), "apiKeyConfigured": bool(value.get("apiKey")),
            "timeoutSeconds": int(value.get("timeoutSeconds", 30))}


@blueprint.get("/settings/rag")
@administrator
def get_rag_settings():
    row = database.session.get(SystemSetting, "rag.connection")
    return jsonify(rag_view(decrypt_json(row.encrypted_value) if row else {}))


@blueprint.put("/settings/rag")
@administrator
def put_rag_settings():
    payload = request.get_json(silent=True) or {}
    base_url = str(payload.get("baseUrl", "")).rstrip("/")
    timeout = payload.get("timeoutSeconds", 30)
    if not valid_url(base_url) or not isinstance(timeout, int) or not 1 <= timeout <= 120:
        return error("INVALID_REQUEST", "Valid base URL and timeout are required", 400)
    existing = database.session.get(SystemSetting, "rag.connection")
    current = decrypt_json(existing.encrypted_value) if existing else {}
    api_key = str(payload.get("apiKey", "")) or current.get("apiKey", "")
    if not api_key:
        return error("INVALID_REQUEST", "RAG API key is required", 400)
    value = {"baseUrl": base_url, "apiKey": api_key, "timeoutSeconds": timeout}
    if existing:
        existing.encrypted_value = encrypt_json(value)
    else:
        database.session.add(SystemSetting(key="rag.connection", encrypted_value=encrypt_json(value)))
    database.session.commit()
    return jsonify(rag_view(value))


def provider_view(provider: AiProvider) -> dict:
    return {"id": provider.id, "providerType": provider.provider_type, "name": provider.name,
            "baseUrl": provider.base_url, "status": provider.status,
            "accounts": [{"id": item.id, "name": item.name,
                          "baseUrl": item.base_url or provider.base_url, "model": item.model, "price": item.price,
                          "concurrencyLimit": item.concurrency_limit, "weight": item.weight,
                          "status": item.status, "apiKeyConfigured": bool(item.encrypted_api_key)}
                         for item in provider.accounts]}


@blueprint.get("/providers")
@administrator
def list_providers():
    return jsonify([provider_view(item) for item in database.session.query(AiProvider).all()])


@blueprint.post("/models/discover")
@administrator
def discover_provider_models():
    payload = request.get_json(silent=True) or {}
    account = database.session.get(AiAccount, payload["accountId"]) if payload.get("accountId") else None
    if payload.get("accountId") and account is None:
        return error("NOT_FOUND", "Provider account not found", 404)
    if account:
        provider = database.session.get(AiProvider, account.provider_id)
        provider_type = provider.provider_type
        base_url = str(payload.get("baseUrl") or account.base_url or provider.base_url).rstrip("/")
        api_key = str(payload.get("apiKey") or cipher().decrypt(account.encrypted_api_key.encode("ascii")).decode("utf-8"))
    else:
        provider_type = str(payload.get("providerType", "")).upper()
        base_url = str(payload.get("baseUrl", "")).rstrip("/")
        api_key = str(payload.get("apiKey", ""))
    if provider_type not in PROVIDER_TYPES or not valid_url(base_url) or not api_key:
        return error("INVALID_REQUEST", "Provider type, URL and API key are required", 400)
    try:
        return jsonify(discover_models(provider_type, base_url, api_key))
    except (httpx.HTTPError, ValueError):
        return error("MODEL_DISCOVERY_FAILED", "Unable to fetch model list from provider", 502)


@blueprint.post("/providers")
@administrator
def create_provider():
    payload = request.get_json(silent=True) or {}
    provider_type = str(payload.get("providerType", "")).upper()
    base_url = str(payload.get("baseUrl", "")).rstrip("/")
    accounts = payload.get("accounts")
    if provider_type not in PROVIDER_TYPES or not valid_url(base_url) or not isinstance(accounts, list) or not accounts:
        return error("INVALID_REQUEST", "Provider type, URL and at least one account are required", 400)
    provider = AiProvider(provider_type=provider_type, name=str(payload.get("name", "")).strip()[:120],
                          base_url=base_url)
    if not provider.name:
        return error("INVALID_REQUEST", "Provider name is required", 400)
    for value in accounts:
        key = str(value.get("apiKey", ""))
        model = str(value.get("model", "")).strip()
        limit = value.get("concurrencyLimit", 2)
        weight = value.get("weight", 1)
        try:
            price = normalized_price(value.get("price"))
        except ValueError:
            return error("INVALID_REQUEST", "Invalid model price", 400)
        if not key or not model or not isinstance(limit, int) or not 1 <= limit <= 100 \
                or not isinstance(weight, int) or not 1 <= weight <= 100:
            return error("INVALID_REQUEST", "Each account requires key, model and valid limits", 400)
        provider.accounts.append(AiAccount(name=str(value.get("name", "Account")).strip()[:120],
                                           encrypted_api_key=encrypt_secret(key), model=model, price=price,
                                           concurrency_limit=limit, weight=weight))
    database.session.add(provider)
    database.session.commit()
    return jsonify(provider_view(provider)), 201


def account_from_payload(payload: dict, provider: AiProvider) -> AiAccount | None:
    key = str(payload.get("apiKey", ""))
    model = str(payload.get("model", "")).strip()
    base_url = str(payload.get("baseUrl", "")).rstrip("/")
    limit = payload.get("concurrencyLimit", 2)
    weight = payload.get("weight", 1)
    try:
        price = normalized_price(payload.get("price"))
    except ValueError:
        return None
    if not key or not model or (base_url and not valid_url(base_url)) \
            or not isinstance(limit, int) or not 1 <= limit <= 100 \
            or not isinstance(weight, int) or not 1 <= weight <= 100:
        return None
    return AiAccount(provider_id=provider.id, name=str(payload.get("name", "Account")).strip()[:120] or "Account",
                     base_url=base_url or None, encrypted_api_key=encrypt_secret(key), model=model[:200], price=price,
                     concurrency_limit=limit, weight=weight)


@blueprint.post("/providers/<provider_id>/accounts")
@administrator
def create_account(provider_id: str):
    provider = database.session.get(AiProvider, provider_id)
    if provider is None:
        return error("NOT_FOUND", "Provider not found", 404)
    account = account_from_payload(request.get_json(silent=True) or {}, provider)
    if account is None:
        return error("INVALID_REQUEST", "Account requires a valid URL, key, model and limits", 400)
    provider.accounts.append(account)
    database.session.commit()
    return jsonify(provider_view(provider)), 201


def user_view(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "status": user.status,
            "passwordChangeRequired": user.password_change_required,
            "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
            "createdAt": user.created_at.isoformat()}


@blueprint.get("/users")
@administrator
def list_users():
    return jsonify([user_view(item) for item in database.session.query(User).order_by(User.created_at).all()])


@blueprint.post("/users")
@administrator
def create_user():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", ""))
    role = str(payload.get("role", "USER")).upper()
    if not username or len(username) > 80 or len(password) < 12 or role not in {"ADMIN", "USER"}:
        return error("INVALID_REQUEST", "Valid username, password and role are required", 400)
    if database.session.query(User).filter_by(username=username).first():
        return error("USERNAME_EXISTS", "Username already exists", 409)
    user = User.create(username, password, role=role, password_change_required=False)
    database.session.add(user)
    database.session.commit()
    return jsonify(user_view(user)), 201


@blueprint.patch("/users/<user_id>")
@administrator
def update_user(user_id: str):
    user = database.session.get(User, user_id)
    if user is None:
        return error("NOT_FOUND", "User not found", 404)
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    role = payload.get("role")
    password = payload.get("password")
    disables_current_admin = user.id == g.current_user.id and (
        (status is not None and str(status).upper() == "DISABLED")
        or (role is not None and str(role).upper() != "ADMIN")
    )
    if disables_current_admin:
        return error("CURRENT_ADMIN_REQUIRED", "Current administrator cannot disable or demote their account", 409)
    if status is not None:
        status = str(status).upper()
        if status not in {"ACTIVE", "DISABLED"}:
            return error("INVALID_REQUEST", "Invalid user status", 400)
        user.status = status
    if role is not None:
        role = str(role).upper()
        if role not in {"ADMIN", "USER"}:
            return error("INVALID_REQUEST", "Invalid user role", 400)
        user.role = role
    if password is not None:
        if len(str(password)) < 12:
            return error("INVALID_REQUEST", "Password must be at least 12 characters", 400)
        from app.models import password_hasher
        user.password_hash = password_hasher.hash(str(password))
        user.password_change_required = True
    database.session.commit()
    return jsonify(user_view(user))


@blueprint.patch("/accounts/<account_id>")
@administrator
def update_account(account_id: str):
    account = database.session.get(AiAccount, account_id)
    if account is None:
        return error("NOT_FOUND", "Provider account not found", 404)
    payload = request.get_json(silent=True) or {}
    if "concurrencyLimit" in payload:
        value = payload["concurrencyLimit"]
        if not isinstance(value, int) or not 1 <= value <= 100:
            return error("INVALID_REQUEST", "Invalid concurrency limit", 400)
        account.concurrency_limit = value
    if "weight" in payload:
        value = payload["weight"]
        if not isinstance(value, int) or not 1 <= value <= 100:
            return error("INVALID_REQUEST", "Invalid account weight", 400)
        account.weight = value
    if "status" in payload:
        value = str(payload["status"]).upper()
        if value not in {"ACTIVE", "DISABLED"}:
            return error("INVALID_REQUEST", "Invalid account status", 400)
        account.status = value
    if "model" in payload and str(payload["model"]).strip():
        account.model = str(payload["model"]).strip()[:200]
    if "price" in payload:
        try:
            account.price = normalized_price(payload["price"])
        except ValueError:
            return error("INVALID_REQUEST", "Invalid model price", 400)
    if "name" in payload:
        value = str(payload["name"]).strip()
        if not value:
            return error("INVALID_REQUEST", "Account name is required", 400)
        account.name = value[:120]
    if "baseUrl" in payload:
        value = str(payload["baseUrl"]).rstrip("/")
        if value and not valid_url(value):
            return error("INVALID_REQUEST", "Invalid account URL", 400)
        account.base_url = value or None
    if payload.get("apiKey"):
        account.encrypted_api_key = encrypt_secret(str(payload["apiKey"]))
    database.session.commit()
    provider = database.session.get(AiProvider, account.provider_id)
    return jsonify(provider_view(provider))


@blueprint.get("/health")
@administrator
def health():
    rag = {"status": "NOT_CONFIGURED", "latencyMs": None}
    setting = database.session.get(SystemSetting, "rag.connection")
    if setting:
        value = decrypt_json(setting.encrypted_value)
        started = time.perf_counter()
        try:
            response = httpx.get(f"{value['baseUrl'].rstrip('/')}/api/v1/consumer/health",
                                 headers={"Authorization": f"Bearer {value['apiKey']}"},
                                 timeout=float(value.get("timeoutSeconds", 30)))
            rag = {"status": "UP" if response.status_code == 200 else "DOWN",
                   "latencyMs": int((time.perf_counter() - started) * 1000)}
        except httpx.HTTPError:
            rag = {"status": "DOWN", "latencyMs": int((time.perf_counter() - started) * 1000)}
    providers = []
    for provider in database.session.query(AiProvider).all():
        accounts = []
        for account in provider.accounts:
            started = time.perf_counter()
            try:
                key = cipher().decrypt(account.encrypted_api_key.encode("ascii")).decode("utf-8")
                base_url = (account.base_url or provider.base_url).rstrip("/")
                response = httpx.get(f"{base_url}/models",
                                     headers={"Authorization": f"Bearer {key}"}, timeout=10)
                status = "UP" if response.status_code == 200 else "DOWN"
            except (httpx.HTTPError, ValueError):
                status = "DOWN"
            accounts.append({"id": account.id, "name": account.name, "status": status,
                             "latencyMs": int((time.perf_counter() - started) * 1000)})
        providers.append({"id": provider.id, "name": provider.name, "accounts": accounts})
    return jsonify({"rag": rag, "providers": providers})


@blueprint.get("/stats")
@administrator
def stats():
    rag_requests = database.session.query(func.count(RagRequest.id)).scalar() or 0
    provider_requests = database.session.query(func.count(ProviderRequest.id)).scalar() or 0
    provider_failures = database.session.query(func.count(ProviderRequest.id)).filter(
        ProviderRequest.status == "FAILED").scalar() or 0
    tokens = database.session.query(func.coalesce(func.sum(
        func.coalesce(ProviderRequest.prompt_tokens, 0) + func.coalesce(ProviderRequest.completion_tokens, 0)), 0)
    ).scalar() or 0
    average_latency = database.session.query(func.avg(ProviderRequest.latency_ms)).filter(
        ProviderRequest.latency_ms.is_not(None)).scalar()
    return jsonify({"ragRequests": rag_requests, "providerRequests": provider_requests,
                    "providerFailures": provider_failures, "tokens": tokens,
                    "averageProviderLatencyMs": round(average_latency or 0),
                    "activeUsers": database.session.query(func.count(User.id)).filter(User.status == "ACTIVE").scalar() or 0})
