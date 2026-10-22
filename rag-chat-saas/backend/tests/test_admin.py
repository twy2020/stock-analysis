from __future__ import annotations

from app.extensions import database
import respx
from httpx import Response

from app.crypto import encrypt_json, encrypt_secret
from app.models import (AiAccount, AiProvider, Conversation, ProviderRequest,
                        RagRequest, SystemSetting, User)


def authenticated_admin(client):
    login = client.post("/api/v1/auth/login", json={
        "username": "admin", "password": "Initial-Password-42!"
    })
    changed = client.post("/api/v1/auth/change-password", json={"password": "Admin-Password-84!"},
                          headers={"X-CSRF-Token": login.json["csrfToken"]})
    return changed.json["csrfToken"]


def test_rag_settings_are_encrypted_and_secret_is_never_returned(app, client):
    csrf = authenticated_admin(client)
    response = client.put("/api/v1/admin/settings/rag", json={
        "baseUrl": "https://rag.internal", "apiKey": "rag_live_secret", "timeoutSeconds": 20
    }, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert response.json == {"baseUrl": "https://rag.internal", "apiKeyConfigured": True,
                             "timeoutSeconds": 20}
    assert "rag_live_secret" not in response.get_data(as_text=True)
    with app.app_context():
        row = database.session.query(SystemSetting).filter_by(key="rag.connection").one()
        assert "rag_live_secret" not in row.encrypted_value

    fetched = client.get("/api/v1/admin/settings/rag")
    assert fetched.json == response.json


def test_provider_accounts_validate_encrypt_and_mask_keys(app, client):
    csrf = authenticated_admin(client)
    created = client.post("/api/v1/admin/providers", json={
        "providerType": "SILICONFLOW", "name": "SiliconFlow 主线路",
        "baseUrl": "https://api.siliconflow.cn/v1",
        "accounts": [{"name": "账号 A", "apiKey": "sk-provider-secret",
                      "model": "deepseek-ai/DeepSeek-V3", "concurrencyLimit": 3, "weight": 2}],
    }, headers={"X-CSRF-Token": csrf})

    assert created.status_code == 201
    assert created.json["providerType"] == "SILICONFLOW"
    assert created.json["accounts"][0]["apiKeyConfigured"] is True
    assert "sk-provider-secret" not in created.get_data(as_text=True)
    with app.app_context():
        account = database.session.query(AiAccount).one()
        assert "sk-provider-secret" not in account.encrypted_api_key

    invalid = client.post("/api/v1/admin/providers", json={
        "providerType": "UNKNOWN", "name": "Bad", "baseUrl": "not-a-url", "accounts": []
    }, headers={"X-CSRF-Token": csrf})
    assert invalid.status_code == 400


@respx.mock
def test_custom_provider_discovers_only_chat_models_and_keeps_manual_price(app, client):
    csrf = authenticated_admin(client)
    catalog = respx.get("https://custom.example/v1/models").mock(return_value=Response(200, json={"data": [
        {"id": "chat-large", "type": "chat"},
        {"id": "embedding-small", "type": "embedding"},
        {"id": "ranker-v1", "type": "rerank"},
    ]}))
    discovered = client.post("/api/v1/admin/models/discover", json={
        "providerType": "OPENAI_COMPATIBLE", "baseUrl": "https://custom.example/v1", "apiKey": "secret-value",
    }, headers={"X-CSRF-Token": csrf})
    assert discovered.status_code == 200
    assert [row["id"] for row in discovered.json["models"]] == ["chat-large"]
    assert discovered.json["models"][0]["price"] is None
    assert catalog.calls[0].request.headers["Authorization"] == "Bearer secret-value"
    assert "secret-value" not in discovered.get_data(as_text=True)

    created = client.post("/api/v1/admin/providers", json={
        "providerType": "OPENAI_COMPATIBLE", "name": "Custom", "baseUrl": "https://custom.example/v1",
        "accounts": [{"name": "Primary", "apiKey": "secret-value", "model": "chat-large",
                      "price": {"currency": "USD", "inputPerMillion": 1.25, "outputPerMillion": 4.5,
                                "source": "manual"}}],
    }, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201
    assert created.json["accounts"][0]["price"]["inputPerMillion"] == 1.25

    existing = client.post("/api/v1/admin/models/discover", json={
        "accountId": created.json["accounts"][0]["id"],
    }, headers={"X-CSRF-Token": csrf})
    assert existing.status_code == 200
    assert catalog.call_count == 2


@respx.mock
def test_openai_catalog_uses_reference_prices_only_when_model_matches(app, client):
    csrf = authenticated_admin(client)
    respx.get("https://api.openai.com/v1/models").mock(return_value=Response(200, json={"data": [
        {"id": "gpt-4o-mini"}, {"id": "text-embedding-3-small"}, {"id": "dall-e-3"},
    ]}))
    respx.get("https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json").mock(
        return_value=Response(200, json={"gpt-4o-mini": {"litellm_provider": "openai", "mode": "chat",
            "input_cost_per_token": 0.00000015, "output_cost_per_token": 0.0000006}}))
    response = client.post("/api/v1/admin/models/discover", json={
        "providerType": "OPENAI", "baseUrl": "https://api.openai.com/v1", "apiKey": "key",
    }, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert [row["id"] for row in response.json["models"]] == ["gpt-4o-mini"]
    assert response.json["models"][0]["price"] == {
        "currency": "USD", "inputPerMillion": 0.15, "outputPerMillion": 0.6,
        "source": "LiteLLM reference",
    }


@respx.mock
def test_siliconflow_catalog_reads_unambiguous_official_prices(app, client):
    csrf = authenticated_admin(client)
    respx.get("https://api.siliconflow.cn/v1/models").mock(return_value=Response(200, json={
        "data": [{"id": "vendor/chat-one"}]}))
    respx.get("https://www.siliconflow.cn/pricing").mock(return_value=Response(200, text='''
        <div id="pricing-row-text-1"><div><a title="vendor/chat-one">Chat One</a></div>
        <div><span>¥ 2.00</span></div><div><span>¥ 8.00</span></div><div>-</div></div>
    '''))
    response = client.post("/api/v1/admin/models/discover", json={
        "providerType": "SILICONFLOW", "baseUrl": "https://api.siliconflow.cn/v1", "apiKey": "key",
    }, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json["models"][0]["price"] == {
        "currency": "CNY", "inputPerMillion": 2.0, "outputPerMillion": 8.0,
        "source": "SiliconFlow official",
    }


def test_admin_appends_account_with_an_independent_endpoint(app, client):
    csrf = authenticated_admin(client)
    provider = client.post("/api/v1/admin/providers", json={
        "providerType": "SILICONFLOW", "name": "SiliconFlow",
        "baseUrl": "https://primary.example/v1",
        "accounts": [{"name": "主账号", "apiKey": "sk-primary", "model": "model-a"}],
    }, headers={"X-CSRF-Token": csrf}).json

    response = client.post(f"/api/v1/admin/providers/{provider['id']}/accounts", json={
        "name": "备用账号", "baseUrl": "https://secondary.example/v1",
        "apiKey": "sk-secondary", "model": "model-b", "concurrencyLimit": 4, "weight": 2,
    }, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 201
    appended = response.json["accounts"][1]
    assert appended["baseUrl"] == "https://secondary.example/v1"
    assert appended["apiKeyConfigured"] is True
    assert "sk-secondary" not in response.get_data(as_text=True)
    with app.app_context():
        account = database.session.get(AiAccount, appended["id"])
        assert account.base_url == "https://secondary.example/v1"
        assert "sk-secondary" not in account.encrypted_api_key

    updated = client.patch(f"/api/v1/admin/accounts/{appended['id']}", json={
        "baseUrl": "https://rotated.example/v1", "apiKey": "sk-rotated", "model": "model-c",
    }, headers={"X-CSRF-Token": csrf})
    assert updated.status_code == 200
    rotated = updated.json["accounts"][1]
    assert rotated["baseUrl"] == "https://rotated.example/v1"
    assert rotated["model"] == "model-c"
    assert "sk-rotated" not in updated.get_data(as_text=True)
    with app.app_context():
        account = database.session.get(AiAccount, appended["id"])
        assert "sk-rotated" not in account.encrypted_api_key


def test_non_admin_cannot_access_admin_api(app, client):
    with app.app_context():
        user = User.create("member", "Member-Password-42!", password_change_required=False)
        database.session.add(user)
        database.session.commit()
    member = app.test_client()
    login = member.post("/api/v1/auth/login", json={"username": "member", "password": "Member-Password-42!"})
    assert login.status_code == 200
    assert member.get("/api/v1/admin/settings/rag").status_code == 403


def test_admin_creates_lists_and_disables_users(app, client):
    csrf = authenticated_admin(client)
    created = client.post("/api/v1/admin/users", json={
        "username": "operator", "password": "Operator-Password-42!", "role": "USER"
    }, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201
    assert created.json["passwordChangeRequired"] is False
    assert "Operator-Password-42!" not in created.get_data(as_text=True)

    member = app.test_client()
    signed_in = member.post("/api/v1/auth/login", json={
        "username": "operator", "password": "Operator-Password-42!"
    })
    assert signed_in.status_code == 200
    assert signed_in.json["user"]["passwordChangeRequired"] is False
    assert member.get("/api/v1/conversations").status_code == 200

    users = client.get("/api/v1/admin/users").json
    assert [item["username"] for item in users] == ["admin", "operator"]
    disabled = client.patch(f"/api/v1/admin/users/{created.json['id']}", json={"status": "DISABLED"},
                            headers={"X-CSRF-Token": csrf})
    assert disabled.status_code == 200 and disabled.json["status"] == "DISABLED"
    assert app.test_client().post("/api/v1/auth/login", json={
        "username": "operator", "password": "Operator-Password-42!"
    }).status_code == 401


def test_admin_cannot_disable_or_demote_their_own_account(app, client):
    csrf = authenticated_admin(client)
    with app.app_context():
        admin = database.session.query(User).filter_by(username="admin").one()
        admin_id = admin.id

    disabled = client.patch(f"/api/v1/admin/users/{admin_id}", json={"status": "DISABLED"},
                            headers={"X-CSRF-Token": csrf})
    demoted = client.patch(f"/api/v1/admin/users/{admin_id}", json={"role": "USER"},
                           headers={"X-CSRF-Token": csrf})

    assert disabled.status_code == 409
    assert disabled.json["code"] == "CURRENT_ADMIN_REQUIRED"
    assert demoted.status_code == 409
    assert demoted.json["code"] == "CURRENT_ADMIN_REQUIRED"

    with app.app_context():
        admin = database.session.get(User, admin_id)
        assert admin.status == "ACTIVE"
        assert admin.role == "ADMIN"


@respx.mock
def test_health_checks_rag_and_provider_accounts_without_leaking_responses(app, client):
    authenticated_admin(client)
    with app.app_context():
        database.session.add(SystemSetting(key="rag.connection", encrypted_value=encrypt_json({
            "baseUrl": "https://rag.internal", "apiKey": "rag-secret", "timeoutSeconds": 5
        })))
        provider = AiProvider(provider_type="DEEPSEEK", name="DeepSeek", base_url="https://model.internal/v1")
        provider.accounts.append(AiAccount(name="primary", encrypted_api_key=encrypt_secret("model-secret"),
                                           model="deepseek-chat", concurrency_limit=2, weight=1))
        database.session.add(provider)
        database.session.commit()
    rag = respx.get("https://rag.internal/api/v1/consumer/health").mock(
        return_value=Response(200, json={"status": "UP", "internal": "must-not-leak"}))
    model = respx.get("https://model.internal/v1/models").mock(
        return_value=Response(200, json={"data": [], "internal": "must-not-leak"}))

    response = client.get("/api/v1/admin/health")
    assert response.status_code == 200
    assert response.json["rag"]["status"] == "UP"
    assert response.json["providers"][0]["accounts"][0]["status"] == "UP"
    assert "must-not-leak" not in response.get_data(as_text=True)
    assert rag.calls[0].request.headers["Authorization"] == "Bearer rag-secret"
    assert model.calls[0].request.headers["Authorization"] == "Bearer model-secret"


@respx.mock
def test_health_uses_the_account_endpoint_override(app, client):
    authenticated_admin(client)
    with app.app_context():
        provider = AiProvider(provider_type="DEEPSEEK", name="DeepSeek",
                              base_url="https://default.example/v1")
        provider.accounts.append(AiAccount(name="secondary", base_url="https://secondary.example/v1",
                                           encrypted_api_key=encrypt_secret("secondary-secret"),
                                           model="deepseek-chat", concurrency_limit=2, weight=1))
        database.session.add(provider)
        database.session.commit()
    request = respx.get("https://secondary.example/v1/models").mock(return_value=Response(200, json={"data": []}))

    response = client.get("/api/v1/admin/health")

    assert response.status_code == 200
    assert response.json["providers"][0]["accounts"][0]["status"] == "UP"
    assert request.called


def test_usage_summary_reports_requests_failures_tokens_and_latency(app, client):
    authenticated_admin(client)
    with app.app_context():
        admin = database.session.query(User).filter_by(username="admin").one()
        conversation = Conversation(organization_id=admin.organization_id, owner_id=admin.id, title="Usage")
        provider = AiProvider(provider_type="DEEPSEEK", name="DeepSeek", base_url="https://model.invalid/v1")
        account = AiAccount(name="primary", encrypted_api_key=encrypt_secret("key"), model="deepseek-chat",
                            concurrency_limit=2, weight=1)
        provider.accounts.append(account)
        database.session.add_all([conversation, provider])
        database.session.flush()
        database.session.add(RagRequest(organization_id=admin.organization_id, user_id=admin.id,
                                        conversation_id=conversation.id, knowledge_base_id="kb-1", query_id="q1",
                                        status="SUCCEEDED", result_count=5, latency_ms=70))
        database.session.add(ProviderRequest(account_id=account.id, user_id=admin.id,
                                             conversation_id=conversation.id, status="SUCCEEDED", latency_ms=210,
                                             prompt_tokens=100, completion_tokens=30))
        database.session.add(ProviderRequest(account_id=account.id, user_id=admin.id,
                                             conversation_id=conversation.id, status="FAILED", latency_ms=40,
                                             error_category="RATE_LIMIT"))
        database.session.commit()

    summary = client.get("/api/v1/admin/stats").json
    assert summary["ragRequests"] == 1
    assert summary["providerRequests"] == 2
    assert summary["providerFailures"] == 1
    assert summary["tokens"] == 130
    assert summary["averageProviderLatencyMs"] == 125
