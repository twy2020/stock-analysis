from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import Forbidden

from app.auth import load_session, require_csrf
from app.config import Config
from app.extensions import database
from app.models import AiAccount, AiProvider, Organization, User
from app.cache import TtlCache


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    database.init_app(app)
    from app.plugins import install as install_plugins
    install_plugins(app)
    app.extensions["knowledge_base_cache"] = TtlCache(
        float(app.config["KNOWLEDGE_BASE_CACHE_TTL_SECONDS"])
    )

    from app.api.auth import blueprint as auth_blueprint
    from app.api.conversations import blueprint as conversations_blueprint
    from app.api.admin import blueprint as admin_blueprint
    from app.api.knowledge import blueprint as knowledge_blueprint
    from app.api.chat import blueprint as chat_blueprint
    from app.api.feedback import blueprint as feedback_blueprint

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(conversations_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(knowledge_blueprint)
    app.register_blueprint(chat_blueprint)
    app.register_blueprint(feedback_blueprint)
    from app.api.message_center import blueprint as message_center_blueprint
    app.register_blueprint(message_center_blueprint)
    from app.api.audit import blueprint as audit_blueprint
    app.register_blueprint(audit_blueprint)
    from app.api.core_callback import blueprint as core_callback_blueprint
    app.register_blueprint(core_callback_blueprint)
    from app.api.web_research import blueprint as web_research_blueprint
    app.register_blueprint(web_research_blueprint)
    from app.stock import blueprint as stock_blueprint
    app.register_blueprint(stock_blueprint)
    app.before_request(load_session)
    app.before_request(require_csrf)
    from app.audit import install_activity_audit
    install_activity_audit(app)

    @app.errorhandler(Forbidden)
    def forbidden(_error):
        return jsonify({"code": "CSRF_REJECTED", "message": "Invalid CSRF token"}), 403

    @app.get("/api/v1/health")
    def health():
        return {"status": "UP", "service": "stock-analysis-saas"}

    with app.app_context():
        database.create_all()
        bootstrap(app)
        bootstrap_provider(app)
    from app.chat_jobs import start_worker
    start_worker(app)
    return app


def bootstrap(app: Flask) -> None:
    if database.session.query(User).count() > 0:
        return
    password = app.config.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not password:
        if app.config["TESTING"]:
            raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD is required")
        return
    organization = Organization(name="Stock Research", **({'id':app.config['BOOTSTRAP_TENANT_ID']} if app.config.get('BOOTSTRAP_TENANT_ID') else {}))
    database.session.add(organization)
    database.session.flush()
    database.session.add(User.create(app.config["BOOTSTRAP_ADMIN_USERNAME"], password,
                                     role="ADMIN", password_change_required=True,
                                     organization_id=organization.id))
    database.session.commit()


def bootstrap_provider(app: Flask) -> None:
    api_key = str(app.config.get("SILICONFLOW_API_KEY", "")).strip()
    if not api_key or database.session.query(AiProvider).count() > 0:
        return
    from app.crypto import encrypt_secret

    provider = AiProvider(
        provider_type="SILICONFLOW",
        name="SiliconFlow",
        base_url=str(app.config.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")).rstrip("/"),
    )
    provider.accounts.append(AiAccount(
        name="主账号",
        encrypted_api_key=encrypt_secret(api_key),
        model=str(app.config.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")),
        concurrency_limit=2,
        weight=1,
    ))
    database.session.add(provider)
    database.session.commit()
