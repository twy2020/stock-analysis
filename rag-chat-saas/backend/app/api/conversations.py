from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from app.auth import authenticated, error
from app.extensions import database
from app.features import rag_enabled
from app.models import Conversation, ProviderRequest, RagRequest, now


blueprint = Blueprint("conversations", __name__, url_prefix="/api/v1/conversations")


def serialize(item: Conversation) -> dict:
    return {"id": item.id, "title": item.title, "knowledgeBaseId": item.knowledge_base_id,
            "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat(),
            'activeRunId':item.active_run_id,'completedRunId':item.completed_run_id,
            'unread':bool(item.completed_run_id and item.completed_run_id != item.seen_run_id)}


def owned_conversation(conversation_id: str) -> Conversation | None:
    return database.session.query(Conversation).filter_by(
        id=conversation_id, organization_id=g.current_user.organization_id, owner_id=g.current_user.id
    ).one_or_none()


@blueprint.get("")
@authenticated
def list_conversations():
    rows = database.session.query(Conversation).filter_by(
        organization_id=g.current_user.organization_id, owner_id=g.current_user.id
    ).order_by(Conversation.updated_at.desc()).all()
    return jsonify([serialize(item) for item in rows])


@blueprint.post("")
@authenticated
def create_conversation():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "新对话")).strip()[:200] or "新对话"
    item = Conversation(organization_id=g.current_user.organization_id, owner_id=g.current_user.id,
                        title=title, knowledge_base_id=payload.get("knowledgeBaseId") if rag_enabled() else None)
    database.session.add(item)
    database.session.commit()
    return jsonify(serialize(item)), 201


@blueprint.get("/<conversation_id>")
@authenticated
def get_conversation(conversation_id: str):
    item = owned_conversation(conversation_id)
    return jsonify(serialize(item)) if item else error("NOT_FOUND", "Conversation not found", 404)


@blueprint.patch("/<conversation_id>")
@authenticated
def update_conversation(conversation_id: str):
    item = owned_conversation(conversation_id)
    if item is None:
        return error("NOT_FOUND", "Conversation not found", 404)
    title = str((request.get_json(silent=True) or {}).get("title", "")).strip()
    if not title or len(title) > 200:
        return error("INVALID_REQUEST", "Conversation title is required", 400)
    item.title = title
    item.updated_at = now()
    database.session.commit()
    return jsonify(serialize(item))


@blueprint.delete("/<conversation_id>")
@authenticated
def delete_conversation(conversation_id: str):
    item = owned_conversation(conversation_id)
    if item is None:
        return error("NOT_FOUND", "Conversation not found", 404)
    if item.active_run_id:
        return error('RUN_ACTIVE','此对话正在回复，请先停止回复',409)
    database.session.query(ProviderRequest).filter_by(
        conversation_id=item.id, user_id=g.current_user.id).delete(synchronize_session=False)
    database.session.query(RagRequest).filter_by(
        conversation_id=item.id, user_id=g.current_user.id).delete(synchronize_session=False)
    database.session.delete(item)
    database.session.commit()
    return "", 204


@blueprint.post('/<conversation_id>/read')
@authenticated
def mark_read(conversation_id):
    item=owned_conversation(conversation_id)
    if item is None: return error('NOT_FOUND','Conversation not found',404)
    run_id=(request.get_json(silent=True) or {}).get('runId')
    if run_id and item.completed_run_id == run_id:
        item.seen_run_id=run_id
        database.session.commit()
    return jsonify(serialize(item))
