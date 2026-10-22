from __future__ import annotations

import respx
from httpx import Response, SyncByteStream

from app.extensions import database
from app.clients.rag import RagClient
from app.crypto import encrypt_json
from app.models import Conversation, Message, MessageCitation, SystemSetting, User


def sign_in(client):
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Initial-Password-42!"})
    changed = client.post("/api/v1/auth/change-password", json={"password": "Admin-Password-84!"},
                          headers={"X-CSRF-Token": login.json["csrfToken"]})
    return changed.json["csrfToken"]


def configure_rag(app):
    with app.app_context():
        database.session.add(SystemSetting(key="rag.connection", encrypted_value=encrypt_json({
            "baseUrl": "https://rag.example", "apiKey": "rag-secret", "timeoutSeconds": 5
        })))
        database.session.commit()


@respx.mock
def test_retrieval_progress_is_yielded_before_upstream_finishes(app):
    configure_rag(app)
    consumed = []

    class Stream(SyncByteStream):
        def __iter__(self):
            consumed.append('progress')
            yield b'event: progress\ndata: {"stage":"RERANK_RUNNING","candidateCount":20}\n\n'
            consumed.append('result')
            yield b'event: retrieval\ndata: {"results":[]}\n\n'

    respx.post('https://rag.example/retrieve/stream').mock(return_value=Response(
        200, headers={'content-type': 'text/event-stream'}, stream=Stream()))
    with app.app_context():
        events = RagClient().retrieve_stream('/retrieve', {'question': 'test'})
        assert next(events) == ('progress', {'stage': 'RERANK_RUNNING', 'candidateCount': 20})
        assert consumed == ['progress']
        assert list(events) == [('retrieval', {'results': []})]


def save_evidence(app, *, owner: User | None = None, query_id="query-1", citation_id="citation-1"):
    with app.app_context():
        owner = owner or database.session.query(User).filter_by(username="admin").one()
        conversation = Conversation(
            organization_id=owner.organization_id, owner_id=owner.id,
            title="Evidence test", knowledge_base_id="kb-1")
        database.session.add(conversation)
        database.session.flush()
        message = Message(
            conversation_id=conversation.id, organization_id=owner.organization_id,
            owner_id=owner.id, role="ASSISTANT", content="answer", status="COMPLETED")
        database.session.add(message)
        database.session.flush()
        database.session.add(MessageCitation(
            message_id=message.id, label=1, query_id=query_id, citation_id=citation_id,
            document_id="doc-1", document_version_id="version-1", title="GB 150",
            file_name="GB150.pdf", media_type="application/pdf", page_start=12, page_end=12,
            passage="设计压力", anchor_json="{}", retrieval_score=.8, rerank_score=.9,
            retrieval_mode="hybrid"))
        database.session.commit()


class TrackingStream(SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.iterated = False
        self.closed = False

    def __iter__(self):
        self.iterated = True
        yield from self.chunks

    def close(self):
        self.closed = True


@respx.mock
def test_document_proxy_defers_upstream_bytes_until_the_response_is_consumed(app):
    configure_rag(app)
    stream = TrackingStream([b"%PDF", b"-document"])
    respx.get("https://rag.example/document").mock(return_value=Response(
        200, stream=stream, headers={"Content-Type": "application/pdf", "Content-Length": "13"}))

    with app.app_context():
        binary = RagClient().binary("/document")
        assert stream.iterated is False
        assert b"".join(binary.content) == b"%PDF-document"
        binary.close()

    assert stream.closed is True


@respx.mock
def test_document_proxy_turns_upstream_partial_default_into_complete_pdf(app, client):
    sign_in(client)
    configure_rag(app)
    save_evidence(app)
    url = "https://rag.example/api/v1/consumer/queries/query-1/citations/citation-1/document"

    def upstream(request):
        requested = request.headers.get("Range")
        if requested is None:
            return Response(206, content=b"%PDF-", headers={
                "Content-Type": "application/pdf", "Content-Range": "bytes 0-4/12",
                "Content-Length": "5", "Accept-Ranges": "bytes",
            })
        assert requested == "bytes=5-11"
        return Response(206, content=b"%%EOF\r\n", headers={
            "Content-Type": "application/pdf", "Content-Range": "bytes 5-11/12",
            "Content-Length": "7", "Accept-Ranges": "bytes",
        })

    respx.get(url).mock(side_effect=upstream)
    response = client.get("/api/v1/evidence/query-1/citation-1/document")

    assert response.status_code == 200
    assert response.headers["Content-Length"] == "12"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert "Content-Range" not in response.headers
    assert response.data == b"%PDF-%%EOF\r\n"


@respx.mock
def test_lists_published_knowledge_bases_without_leaking_key(app, client):
    sign_in(client)
    configure_rag(app)
    upstream = respx.get("https://rag.example/api/v1/consumer/knowledge-bases").mock(
        return_value=Response(200, json=[{"id": "kb-1", "name": "规范库", "versionNumber": 3,
                                         "publicationRevision": 8, "updatedAt": "2026-09-24T00:00:00Z"}]))

    response = client.get("/api/v1/knowledge-bases")
    cached = client.get("/api/v1/knowledge-bases")

    assert response.status_code == 200
    assert cached.json == response.json
    assert response.json[0]["name"] == "规范库"
    assert len(upstream.calls) == 1
    assert upstream.calls[0].request.headers["Authorization"] == "Bearer rag-secret"
    assert "rag-secret" not in response.get_data(as_text=True)


@respx.mock
def test_retrieval_preserves_passage_models_scores_and_citation_coordinates(app, client):
    csrf = sign_in(client)
    configure_rag(app)
    body = {"requestId": "req-1", "queryId": "query-1", "knowledgeBaseId": "kb-1",
            "mode": "hybrid", "topK": 5, "durationMs": 83,
            "stages": [{"type": "rerank", "embeddingModel": "bge-m3", "rerankModel": "bge-reranker-v2-m3",
                        "status": "SUCCEEDED", "durationMs": 21}],
            "results": [{"rank": 1, "citationId": "citation-1", "passage": "完整召回内容",
                         "snippet": "召回内容", "retrievalScore": 0.82, "rerankScore": 0.94,
                         "channelScores": {"dense": 0.82}, "retrievalMode": "hybrid",
                         "document": {"id": "doc-1", "versionId": "version-1", "title": "GB 150",
                                      "fileName": "GB150.pdf", "mediaType": "application/pdf"},
                         "page": {"start": 12, "end": 13, "anchor": {"pageNumber": 12}}}]}
    respx.post("https://rag.example/api/v1/consumer/knowledge-bases/kb-1/retrieve").mock(
        return_value=Response(200, json=body))

    response = client.post("/api/v1/retrieval", json={
        "knowledgeBaseId": "kb-1", "question": "设计压力如何确定？", "topK": 5, "mode": "hybrid"
    }, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert response.json == body
    assert response.json["results"][0]["passage"] == "完整召回内容"
    assert response.json["stages"][0]["rerankModel"] == "bge-reranker-v2-m3"


@respx.mock
def test_evidence_metadata_and_document_range_are_proxied_for_exact_pair(app, client):
    sign_in(client)
    configure_rag(app)
    save_evidence(app)
    page_url = "https://rag.example/api/v1/consumer/queries/query-1/citations/citation-1/page"
    document_url = page_url.removesuffix("/page") + "/document"
    respx.get(page_url).mock(return_value=Response(200, json={
        "queryId": "query-1", "citationId": "citation-1", "pageNumber": 12,
        "highlightMode": "EXACT", "regions": [{"x": .1, "y": .2, "width": .3, "height": .1}],
        "matchedText": "设计压力", "contentUrl": "/internal", "documentUrl": "/internal-doc"
    }))
    document = respx.get(document_url).mock(return_value=Response(
        206, content=b"%PDF", headers={"Content-Type": "application/pdf", "Content-Range": "bytes 0-3/100",
                                       "Accept-Ranges": "bytes", "Content-Disposition": "inline"}))

    page = client.get("/api/v1/evidence/query-1/citation-1/page")
    content = client.get("/api/v1/evidence/query-1/citation-1/document", headers={"Range": "bytes=0-3"})

    assert page.status_code == 200 and page.json["pageNumber"] == 12
    assert content.status_code == 206 and content.data == b"%PDF"
    assert content.headers["Content-Range"] == "bytes 0-3/100"
    assert document.calls[0].request.headers["Range"] == "bytes=0-3"


@respx.mock
def test_evidence_proxy_rejects_a_citation_owned_by_another_user(app, client):
    sign_in(client)
    configure_rag(app)
    with app.app_context():
        other = User.create("other-user", "Other-Password-42!", password_change_required=False)
        database.session.add(other)
        database.session.commit()
        other_id = other.id
    with app.app_context():
        save_evidence(app, owner=database.session.get(User, other_id))
    upstream = respx.get(
        "https://rag.example/api/v1/consumer/queries/query-1/citations/citation-1/page"
    ).mock(return_value=Response(200, json={"pageNumber": 12}))

    response = client.get("/api/v1/evidence/query-1/citation-1/page")

    assert response.status_code == 404
    assert response.json["code"] == "EVIDENCE_NOT_FOUND"
    assert len(upstream.calls) == 0


@respx.mock
def test_upstream_failure_is_mapped_without_returning_internal_body(app, client):
    sign_in(client)
    configure_rag(app)
    respx.get("https://rag.example/api/v1/consumer/knowledge-bases").mock(
        return_value=Response(503, text="upstream internal topology"))
    response = client.get("/api/v1/knowledge-bases")
    assert response.status_code == 503
    assert response.json["code"] == "RAG_UNAVAILABLE"
    assert "topology" not in response.get_data(as_text=True)
