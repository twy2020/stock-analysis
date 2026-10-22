from __future__ import annotations

from flask import Blueprint, Response, current_app, g, jsonify, request

from app.auth import authenticated, error
from app.clients.rag import RagClient, RagClientError
from app.extensions import database
from app.features import rag_enabled
from app.models import Message, MessageCitation


blueprint = Blueprint("knowledge", __name__, url_prefix="/api/v1")


def invoke(operation):
    try:
        return operation(RagClient())
    except RagClientError as exc:
        code = "EVIDENCE_NOT_FOUND" if exc.status == 404 else "RAG_UNAVAILABLE"
        message = "Evidence is unavailable" if exc.status == 404 else "Knowledge service is unavailable"
        return error(code, message, exc.status)


@blueprint.get("/knowledge-bases")
@authenticated
def knowledge_bases():
    if not rag_enabled(): return jsonify([])
    def load(client: RagClient):
        cache = current_app.extensions["knowledge_base_cache"]
        value = cache.get_or_load(client.cache_key, lambda: client.json(
            "GET", "/api/v1/consumer/knowledge-bases"))
        return jsonify(value)
    return invoke(load)


@blueprint.post("/retrieval")
@authenticated
def retrieve():
    if not rag_enabled(): return error('RAG_DISABLED','知识库检索已关闭',403)
    payload = request.get_json(silent=True) or {}
    knowledge_base_id = str(payload.pop("knowledgeBaseId", ""))
    if not knowledge_base_id:
        return error("INVALID_REQUEST", "Knowledge base is required", 400)
    return invoke(lambda client: jsonify(client.json(
        "POST", f"/api/v1/consumer/knowledge-bases/{knowledge_base_id}/retrieve", payload)))


def evidence_path(query_id: str, citation_id: str, suffix: str) -> str:
    return f"/api/v1/consumer/queries/{query_id}/citations/{citation_id}/{suffix}"


def owns_evidence(query_id: str, citation_id: str) -> bool:
    return database.session.query(MessageCitation.id).join(
        Message, Message.id == MessageCitation.message_id
    ).filter(
        MessageCitation.query_id == query_id,
        MessageCitation.citation_id == citation_id,
        Message.organization_id == g.current_user.organization_id,
        Message.owner_id == g.current_user.id,
    ).first() is not None


def evidence_not_found():
    return error("EVIDENCE_NOT_FOUND", "Evidence is unavailable", 404)


@blueprint.get("/evidence/<query_id>/<citation_id>/pages")
@blueprint.get("/evidence/<query_id>/<citation_id>/pages/<int:page>")
@blueprint.get("/evidence/<query_id>/<citation_id>/pages/<int:page>/image")
@authenticated
def evidence_images(query_id: str, citation_id: str, page: int | None = None):
    if not owns_evidence(query_id, citation_id):
        return evidence_not_found()
    suffix = "pages" if page is None else f"pages/{page}"
    if request.path.endswith("/image"):
        return invoke(lambda client: binary_response(client.binary(evidence_path(query_id, citation_id, suffix + "/image"), None)))
    return invoke(lambda client: jsonify(client.json("GET", evidence_path(query_id, citation_id, suffix))))


@blueprint.get("/evidence/<query_id>/<citation_id>/page")
@authenticated
def evidence_page(query_id: str, citation_id: str):
    if not owns_evidence(query_id, citation_id):
        return evidence_not_found()
    def load(client: RagClient):
        payload = client.json("GET", evidence_path(query_id, citation_id, "page"))
        base = f"/api/v1/evidence/{query_id}/{citation_id}"
        payload["contentUrl"] = f"{base}/page/content"
        payload["documentUrl"] = f"{base}/document"
        return jsonify(payload)
    return invoke(load)


def binary_response(binary):
    response = Response(binary.content, status=binary.status, direct_passthrough=True)
    for name, value in binary.headers.items():
        response.headers[name] = value
    response.headers["Cache-Control"] = "no-store"
    response.call_on_close(binary.close)
    return response


@blueprint.get("/evidence/<query_id>/<citation_id>/page/content")
@authenticated
def evidence_page_content(query_id: str, citation_id: str):
    if not owns_evidence(query_id, citation_id):
        return evidence_not_found()
    return invoke(lambda client: binary_response(client.binary(
        evidence_path(query_id, citation_id, "page/content"), request.headers.get("Range"))))


@blueprint.get("/evidence/<query_id>/<citation_id>/document")
@authenticated
def evidence_document(query_id: str, citation_id: str):
    if not owns_evidence(query_id, citation_id):
        return evidence_not_found()
    return invoke(lambda client: binary_response(client.binary(
        evidence_path(query_id, citation_id, "document"), request.headers.get("Range"))))
