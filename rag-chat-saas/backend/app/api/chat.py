from __future__ import annotations

import json
import time
from datetime import timedelta

from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context

from app.auth import authenticated, error
from app.chat import ChatService
from app.clients.openai_compatible import thinking_control
from app.provider_pool import provider_pool
from app.extensions import database
from app.features import rag_enabled, web_enabled
from app.models import Conversation, Message, MessageCitation, ProviderRequest, ChatRun, ChatRunEvent, now
from app.chat_jobs import enqueue, RunConflict, run_payload


blueprint = Blueprint("chat", __name__, url_prefix="/api/v1/conversations")


@blueprint.get('/capabilities')
@authenticated
def capabilities():
    from app.core_client import enabled, CoreClient, CoreError
    if enabled():
        try:
            result = CoreClient().request('GET', '/v1/capabilities')
            return jsonify({'reasoningToggle': bool(result.get('reasoningToggle')), 'backend': 'core', 'ragAvailable':rag_enabled(),
                            'modelProfile':result.get('defaultModelProfile'),
                            'model':next((m.get('model') for m in result.get('models',[]) if m.get('id')==result.get('defaultModelProfile')),None),
                            'webAvailable':web_enabled() and any(t.get('name')=='stock_web_fetch' for t in result.get('tools',[])), 'stockAnalysis':True})
        except CoreError:
            return jsonify({'reasoningToggle': False, 'backend': 'core', 'available': False, 'ragAvailable':rag_enabled(),'stockAnalysis':True})
    return jsonify({'ragAvailable':rag_enabled(),'stockAnalysis':True,'reasoningToggle': any(thinking_control(provider.provider_type, account.model)
        for account, provider in provider_pool.candidates())})


def owned(conversation_id: str):
    return database.session.query(Conversation).filter_by(
        id=conversation_id, organization_id=g.current_user.organization_id, owner_id=g.current_user.id
    ).one_or_none()


@blueprint.get("/<conversation_id>/messages")
@authenticated
def messages(conversation_id: str):
    conversation = owned(conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "Conversation not found", 404)
    cutoff = now() - timedelta(minutes=5)
    abandoned = database.session.query(Message).filter_by(
        conversation_id=conversation_id, organization_id=g.current_user.organization_id,
        owner_id=g.current_user.id, role="ASSISTANT", status="STREAMING",
    ).filter(Message.created_at < cutoff, ~Message.id.in_(database.session.query(ChatRun.assistant_message_id)
        .filter(ChatRun.status.in_(['QUEUED','RUNNING'])))).update({Message.status: "FAILED"}, synchronize_session=False)
    if abandoned:
        database.session.query(ProviderRequest).filter_by(
            conversation_id=conversation_id, user_id=g.current_user.id, status="RUNNING",
        ).filter(ProviderRequest.created_at < cutoff).update({
            ProviderRequest.status: "FAILED", ProviderRequest.error_category: "STREAM_INTERRUPTED",
        }, synchronize_session=False)
        database.session.commit()
    rows = database.session.query(Message).filter_by(
        conversation_id=conversation_id, organization_id=g.current_user.organization_id,
        owner_id=g.current_user.id).order_by(Message.created_at).all()
    result = []
    for item in rows:
        from app.plugins.images import message_images
        citations = database.session.query(MessageCitation).filter_by(message_id=item.id).order_by(
            MessageCitation.label).all()
        retrieval = json.loads(item.retrieval_json) if item.retrieval_json else None
        if retrieval:
            stages = retrieval.get("stages", [])
            retrieval["embeddingModel"] = next((stage.get("embeddingModel") for stage in stages
                                                 if stage.get("embeddingModel")), None)
            retrieval["rerankModel"] = next((stage.get("rerankModel") for stage in stages
                                              if stage.get("rerankModel")), None)
        result.append({"id": item.id, "role": item.role, "content": item.content, "status": item.status,
                       "images": message_images(item.id),
                       'parentMessageId':item.parent_message_id,'vote':item.vote,
                       "reasoningContent": (retrieval or {}).get("reasoningContent", ""),
                       "processEvents": (retrieval or {}).get("processEvents", []),
                       "stockArtifacts": (retrieval or {}).get("stockArtifacts", []),
                       "reasoningEnabled": (retrieval or {}).get("reasoningEnabled"),
                       "model": item.model, "createdAt": item.created_at.isoformat(), "retrieval": retrieval,
                       "citations": [{"label": row.label, "queryId": row.query_id,
                                      "citationId": row.citation_id, "title": row.title,
                                      "fileName": row.file_name, "pageStart": row.page_start,
                                      "pageEnd": row.page_end, "passage": row.passage,
                                      "retrievalScore": row.retrieval_score, "rerankScore": row.rerank_score,
                                      "retrievalMode": row.retrieval_mode} for row in citations]})
    return jsonify(result)


@blueprint.post("/<conversation_id>/messages")
@authenticated
def create_message(conversation_id: str):
    response = create_run(conversation_id)
    if isinstance(response,tuple): return response
    job_id=response.get_json()['id']
    return stream_run(conversation_id,job_id)


@blueprint.post('/<conversation_id>/runs')
@authenticated
def create_run(conversation_id):
    conversation = owned(conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "Conversation not found", 404)
    payload = request.get_json(silent=True) or {}
    try:
        job=enqueue(conversation,g.current_user,payload)
        return jsonify(run_payload(job))
    except RunConflict as exc:
        database.session.rollback()
        return error('RUN_ACTIVE',str(exc),409)
    except (ValueError,TypeError) as exc:
        database.session.rollback()
        return error('INVALID_REQUEST',str(exc),400)


def owned_run(conversation_id,run_id):
    if owned(conversation_id) is None: return None
    return database.session.query(ChatRun).filter_by(id=run_id,conversation_id=conversation_id,owner_id=g.current_user.id).one_or_none()


@blueprint.get('/<conversation_id>/runs/<run_id>')
@authenticated
def get_run(conversation_id,run_id):
    job=owned_run(conversation_id,run_id)
    return jsonify(run_payload(job)) if job else error('NOT_FOUND','Task not found',404)


@blueprint.post('/<conversation_id>/runs/<run_id>/cancel')
@authenticated
def cancel_run(conversation_id,run_id):
    job=owned_run(conversation_id,run_id)
    if not job: return error('NOT_FOUND','Task not found',404)
    if job.status in ('QUEUED','RUNNING'):
        job.cancel_requested=True
        database.session.commit()
    if job.status in ('QUEUED','RUNNING','FAILED','CANCELLED'):
        from app.core_client import cancel_chat_run, CoreError
        try: cancel_chat_run(job)
        except CoreError: pass  # Durable flag remains; the attached stream also propagates cancel.
    return jsonify(run_payload(job))


@blueprint.get('/<conversation_id>/runs/<run_id>/events')
@authenticated
def stream_run(conversation_id,run_id):
    if not owned_run(conversation_id,run_id): return error('NOT_FOUND','Task not found',404)
    try: cursor=max(0,int(request.args.get('after',request.headers.get('Last-Event-ID','0'))))
    except ValueError: return error('INVALID_REQUEST','Invalid event cursor',400)
    def events():
        nonlocal cursor
        last_ping=0
        while True:
            rows=database.session.query(ChatRunEvent).filter(ChatRunEvent.run_id==run_id,ChatRunEvent.id>cursor)
            rows=rows.order_by(ChatRunEvent.id).limit(200).all()
            status=database.session.query(ChatRun.status).filter_by(id=run_id).scalar()
            data=[(r.id,r.name,r.payload) for r in rows]
            database.session.remove()
            for seq,name,payload in data:
                cursor=seq
                body=json.dumps({**payload,'eventId':seq},ensure_ascii=False,separators=(',',':'))
                yield f'id: {seq}\nevent: {name}\ndata: {body}\n\n'
                if name in ('complete','error'): return
            if not data and status not in ('QUEUED','RUNNING'):
                yield 'event: error\ndata: {"code":"TASK_ENDED","retryable":true}\n\n'
                return
            if time.monotonic()-last_ping>10:
                yield ': keepalive\n\n'; last_ping=time.monotonic()
            time.sleep(.1)
    return Response(stream_with_context(events()),mimetype='text/event-stream',
                    headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@blueprint.post('/<conversation_id>/messages/<message_id>/vote')
@authenticated
def vote_message(conversation_id,message_id):
    if not owned(conversation_id): return error('NOT_FOUND','Conversation not found',404)
    message=database.session.query(Message).filter_by(id=message_id,conversation_id=conversation_id,role='ASSISTANT').one_or_none()
    if not message: return error('NOT_FOUND','Message not found',404)
    vote=(request.get_json(silent=True) or {}).get('vote')
    if type(vote) is not int or vote not in (-1,0,1): return error('INVALID_REQUEST','Invalid vote',400)
    if message.status=='STREAMING': return error('RUN_ACTIVE','请等待回答完成',409)
    message.vote=vote; database.session.commit()
    return jsonify({'vote':vote})
