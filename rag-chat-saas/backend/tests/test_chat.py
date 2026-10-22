from __future__ import annotations

import json
from datetime import timedelta

import respx
import pytest
from httpx import Response

from app.crypto import encrypt_json, encrypt_secret
from app.clients.openai_compatible import OpenAICompatibleClient, ProviderError
from app.extensions import database
from app.models import (AiAccount, AiProvider, Message, MessageCitation, ProviderRequest,
                        SystemSetting, User, now)
from app.provider_pool import provider_pool


@pytest.fixture(autouse=True)
def execute_submitted_jobs(app, monkeypatch):
    # Provider contract tests run the durable worker deterministically; concurrency has separate tests.
    from app.chat_jobs import enqueue, execute_run
    def submit(*args, **kwargs):
        job=enqueue(*args, **kwargs)
        execute_run(app,job.id)
        return job
    monkeypatch.setattr('app.api.chat.enqueue',submit)


def sign_in(client, username="admin", password="Initial-Password-42!", change=True):
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if not change:
        return login.json["csrfToken"]
    changed = client.post("/api/v1/auth/change-password", json={"password": "Admin-Password-84!"},
                          headers={"X-CSRF-Token": login.json["csrfToken"]})
    return changed.json["csrfToken"]


def configure_dependencies(app, two_accounts=False):
    with app.app_context():
        database.session.add(SystemSetting(key="rag.connection", encrypted_value=encrypt_json({
            "baseUrl": "https://rag.example", "apiKey": "rag-secret", "timeoutSeconds": 5
        })))
        provider = AiProvider(provider_type="DEEPSEEK", name="DeepSeek", base_url="https://model.example/v1")
        provider.accounts.append(AiAccount(name="primary", encrypted_api_key=encrypt_secret("model-key-1"),
                                           model="deepseek-chat", concurrency_limit=1, weight=2))
        if two_accounts:
            provider.accounts.append(AiAccount(name="fallback", encrypted_api_key=encrypt_secret("model-key-2"),
                                               model="deepseek-chat", concurrency_limit=1, weight=1))
        database.session.add(provider)
        database.session.commit()


def tool_then_answer(answer):
    def respond(request):
        messages = json.loads(request.content)['messages']
        if any(item['role'] == 'tool' for item in messages): return answer
        delta = {'tool_calls': [{'index': 0, 'id': 'recall-1', 'type': 'function',
                 'function': {'name': 'recall', 'arguments': json.dumps({'question': '设计压力'})}}]}
        return Response(200, text='data: ' + json.dumps({'choices': [{'delta': delta}]}) + '\n\ndata: [DONE]\n\n')
    return respond


@pytest.mark.parametrize('provider_type,model,enabled,setting', [
    ('DEEPSEEK', 'deepseek-flash', True, {'thinking': {'type': 'enabled'}}),
    ('DEEPSEEK', 'deepseek-flash', False, {'thinking': {'type': 'disabled'}}),
    ('SILICONFLOW', 'deepseek-ai/DeepSeek-V4-Flash', True, {'enable_thinking': True}),
    ('SILICONFLOW', 'deepseek-ai/DeepSeek-V4-Flash', False, {'enable_thinking': False}),
])
@respx.mock
def test_thinking_selection_reaches_provider_and_stream_metadata(app, client, provider_type, model, enabled, setting):
    csrf = sign_in(client)
    configure_dependencies(app)
    with app.app_context():
        database.session.query(AiProvider).one().provider_type = provider_type
        database.session.query(AiAccount).one().model = model
        database.session.commit()
    assert client.get('/api/v1/conversations/capabilities').json['reasoningToggle'] is True
    conversation = client.post('/api/v1/conversations', json={'title': 'Thinking', 'knowledgeBaseId': 'kb-1'},
                               headers={'X-CSRF-Token': csrf}).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    upstream = respx.post('https://model.example/v1/chat/completions').mock(side_effect=tool_then_answer(Response(
        200, text='data: {"choices":[{"delta":{"content":"回答 [1]"}}]}\n\ndata: [DONE]\n\n')))
    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
        json={'content': '问题', 'reasoningEnabled': enabled}, headers={'X-CSRF-Token': csrf}, buffered=True)
    assert 'event: complete' in response.get_data(as_text=True)
    sent = json.loads(upstream.calls[0].request.content)
    for key, value in setting.items():
        assert sent[key] == value
    assert sent['stream'] is True
    assert f'"reasoningEnabled":{str(enabled).lower()}' in response.get_data(as_text=True)


def retrieval_payload():
    return {"requestId": "request-1", "queryId": "query-1", "knowledgeBaseId": "kb-1",
            "mode": "hybrid", "topK": 5, "durationMs": 50,
            "stages": [{"type": "rerank", "embeddingModel": "bge-m3", "rerankModel": "bge-reranker",
                        "status": "SUCCEEDED", "durationMs": 12}],
            "results": [{"rank": 1, "citationId": "citation-1", "passage": "设计压力应根据工况确定。",
                         "snippet": "设计压力应根据工况确定。", "retrievalScore": .8, "rerankScore": .93,
                         "channelScores": {"dense": .8}, "retrievalMode": "hybrid",
                         "document": {"id": "doc-1", "versionId": "ver-1", "title": "压力容器规范",
                                      "fileName": "GB150.pdf", "mediaType": "application/pdf"},
                         "page": {"start": 12, "end": 12, "anchor": {"pageNumber": 12}}}]}


def retrieval_stream_response():
    from app.chat import event
    return Response(200, headers={'Content-Type': 'text/event-stream'}, text=
        event('progress', {'stage': 'RETRIEVE_FUSED', 'candidateCount': 20}) +
        event('progress', {'stage': 'RERANK', 'candidateCount': 8}) +
        event('retrieval', retrieval_payload()))


@respx.mock
def test_grounded_stream_persists_messages_and_citations(app, client):
    csrf = sign_in(client)
    configure_dependencies(app)
    conversation = client.post("/api/v1/conversations", json={"title": "设计压力", "knowledgeBaseId": "kb-1"},
                               headers={"X-CSRF-Token": csrf}).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    provider = respx.post("https://model.example/v1/chat/completions").mock(side_effect=tool_then_answer(Response(
        200, headers={"Content-Type": "text/event-stream"},
        text='data: {"choices":[{"delta":{"content":"设计压力按工况确定"}}]}\n\n'
             'data: {"choices":[{"delta":{"content":" [1]"}}]}\n\n'
             'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":30,"completion_tokens":8}}\n\n'
             'data: [DONE]\n\n')))

    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"content": "如何确定设计压力？"},
                           headers={"X-CSRF-Token": csrf}, buffered=True)

    body = response.get_data(as_text=True)
    assert response.status_code == 200 and response.mimetype == "text/event-stream"
    assert "event: delta" in body and "设计压力按工况确定" in body, body
    assert "event: complete" in body and "citation-1" in body
    assert body.index('"stage":"SEARCHING"') < body.index('event: retrieval')
    assert body.index('event: retrieval') < body.index('event: delta')
    assert 'event: model' in body and '"model":"deepseek-chat"' in body
    sent = json.loads(provider.calls[-1].request.content)
    assert "设计压力应根据工况确定" in sent["messages"][-1]["content"]
    assert sum("如何确定设计压力？" in (item["content"] or '') for item in sent["messages"]) == 1
    assert sent["stream"] is True
    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json
    assert history[1]["citations"][0]["citationId"] == "citation-1"
    assert history[1]["retrieval"]["rerankModel"] == "bge-reranker"


@respx.mock
def test_reasoning_model_streams_provider_reasoning_and_persists_history(app, client):
    csrf = sign_in(client)
    configure_dependencies(app)
    with app.app_context():
        account = database.session.query(AiAccount).one()
        account.model = "deepseek-reasoner"
        database.session.commit()
    conversation = client.post("/api/v1/conversations", json={"title": "Reasoning", "knowledgeBaseId": "kb-1"},
                               headers={"X-CSRF-Token": csrf}).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    respx.post("https://model.example/v1/chat/completions").mock(side_effect=tool_then_answer(Response(
        200, headers={"Content-Type": "text/event-stream"},
        text='data: {"choices":[{"delta":{"reasoning_content":"private thought"}}]}\n\n'
             'data: {"choices":[{"delta":{"content":"回答 [1]"}}]}\n\n'
             'data: [DONE]\n\n')))
    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"content": "问题"},
                           headers={"X-CSRF-Token": csrf}, buffered=True)
    body = response.get_data(as_text=True)
    assert '"reasoningEnabled":true' in body
    assert "event: reasoning" in body
    assert "private thought" in body
    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json
    assert history[1]['reasoningContent'] == 'private thought'
    assert any(item['stage'] == 'RETRIEVE_FUSED' for item in history[1]['processEvents'])

    with app.app_context():
        messages = database.session.query(Message).order_by(Message.created_at).all()
        assert [(item.role, item.status) for item in messages] == [("USER", "COMPLETED"), ("ASSISTANT", "COMPLETED")]
        assert messages[1].content.endswith("[1]")
        citation = database.session.query(MessageCitation).one()
        assert citation.query_id == "query-1" and citation.citation_id == "citation-1"


def test_message_history_is_owner_scoped(app, client):
    csrf = sign_in(client)
    conversation = client.post("/api/v1/conversations", json={"title": "Private"},
                               headers={"X-CSRF-Token": csrf}).json
    with app.app_context():
        other = User.create("other", "Other-Password-42!", password_change_required=False)
        database.session.add(other)
        database.session.commit()
    other_client = app.test_client()
    sign_in(other_client, "other", "Other-Password-42!", change=False)
    assert other_client.get(f"/api/v1/conversations/{conversation['id']}/messages").status_code == 404


def test_history_recovers_an_abandoned_answer(app, client):
    csrf = sign_in(client)
    configure_dependencies(app)
    conversation = client.post("/api/v1/conversations", json={"title": "Stale", "knowledgeBaseId": "kb-1"},
                               headers={"X-CSRF-Token": csrf}).json
    with app.app_context():
        user = database.session.query(User).filter_by(username="admin").one()
        account = database.session.query(AiAccount).one()
        old = now() - timedelta(minutes=10)
        assistant = Message(conversation_id=conversation["id"], organization_id=user.organization_id,
                            owner_id=user.id, role="ASSISTANT", content="", status="STREAMING", created_at=old)
        provider_request = ProviderRequest(account_id=account.id, user_id=user.id,
                                           conversation_id=conversation["id"], status="RUNNING", created_at=old)
        database.session.add_all([assistant, provider_request])
        database.session.commit()

    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json
    assert history[0]["status"] == "FAILED"
    with app.app_context():
        assert database.session.query(ProviderRequest).one().status == "FAILED"


@respx.mock
def test_closing_completed_observer_does_not_cancel_background_answer(app, client):
    csrf = sign_in(client)
    configure_dependencies(app)
    conversation = client.post("/api/v1/conversations", json={"title": "Disconnect", "knowledgeBaseId": "kb-1"},
                               headers={"X-CSRF-Token": csrf}).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    respx.post("https://model.example/v1/chat/completions").mock(return_value=Response(
        200, headers={"Content-Type": "text/event-stream"},
        text='data: {"choices":[{"delta":{"content":"部分回答"}}]}\n\n'
             'data: [DONE]\n\n'))

    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                           json={"content": "问题"}, headers={"X-CSRF-Token": csrf}, buffered=False)
    for block in response.response:
        if b"event: delta" in block:
            break
    response.close()

    with app.app_context():
        assistant = database.session.query(Message).filter_by(role="ASSISTANT").one()
        provider_request = database.session.query(ProviderRequest).one()
        assert assistant.status == "COMPLETED"
        assert provider_request.status == "SUCCEEDED"


def test_provider_pool_excludes_accounts_while_they_are_cooling_down(app):
    configure_dependencies(app, two_accounts=True)
    with app.app_context():
        accounts = database.session.query(AiAccount).order_by(AiAccount.created_at).all()
        accounts[0].cooldown_until = now() + timedelta(seconds=30)
        database.session.commit()

        candidates = provider_pool.candidates()

        assert [account.id for account, _provider in candidates] == [accounts[1].id]


@respx.mock
def test_transient_provider_failure_cools_account_and_fails_over(app, client):
    csrf = sign_in(client)
    configure_dependencies(app, two_accounts=True)
    conversation = client.post("/api/v1/conversations", json={"title": "Failover", "knowledgeBaseId": "kb-1"},
                               headers={"X-CSRF-Token": csrf}).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    calls = iter([
        Response(429, json={"error": {"message": "rate limited"}}),
        Response(200, headers={"Content-Type": "text/event-stream"},
                 text='data: {"choices":[{"delta":{"content":"你好"}}]}\n\ndata: [DONE]\n\n'),
    ])
    route = respx.post("https://model.example/v1/chat/completions").mock(side_effect=lambda _request: next(calls))

    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json={"content": "问题"},
                           headers={"X-CSRF-Token": csrf}, buffered=True)
    assert response.status_code == 200 and "event: complete" in response.get_data(as_text=True)
    assert len(route.calls) == 2
    assert route.calls[0].request.headers["Authorization"] != route.calls[1].request.headers["Authorization"]


@respx.mock
def test_partial_model_stream_is_not_combined_with_a_fallback_account(app, client, monkeypatch):
    csrf = sign_in(client)
    configure_dependencies(app, two_accounts=True)
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Partial stream", "knowledgeBaseId": "kb-1"},
        headers={"X-CSRF-Token": csrf},
    ).json
    respx.post('https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve/stream').mock(
        return_value=retrieval_stream_response())
    attempts: list[str] = []

    def interrupted_stream(self, provider, account, messages, **options):
        attempts.append(account.id)
        yield {"type": "delta", "content": "半段回答"}
        raise ProviderError("UPSTREAM", True)

    monkeypatch.setattr(OpenAICompatibleClient, "stream", interrupted_stream)
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "问题"},
        headers={"X-CSRF-Token": csrf},
        buffered=True,
    )

    body = response.get_data(as_text=True)
    assert len(attempts) == 1
    assert "半段回答" in body
    assert "event: error" in body
    assert "event: complete" not in body
    with app.app_context():
        assistant = database.session.query(Message).filter_by(role="ASSISTANT").one()
        assert assistant.status == "FAILED"
        assert assistant.content == "半段回答"
