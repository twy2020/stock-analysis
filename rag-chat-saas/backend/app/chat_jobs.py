from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import update, select
from app.extensions import database
from app.models import ChatRun, ChatRunEvent, Conversation, Message, MessageCitation, User, AuditRecord, now


class RunConflict(ValueError):
    pass


def enqueue(conversation, user, payload):
    run_id = str(uuid.UUID(payload['requestId'])) if payload.get('requestId') else str(uuid.uuid4())
    existing = database.session.get(ChatRun, run_id)
    if existing:
        if existing.owner_id != user.id or existing.conversation_id != conversation.id:
            raise RunConflict('请求标识已使用')
        return existing
    reasoning = payload.get('reasoningEnabled')
    if reasoning is not None and not isinstance(reasoning, bool): raise ValueError('思考选项无效')
    web = payload.get('webEnabled', False)
    if type(web) is not bool: raise ValueError('联网选项无效')
    from app.features import web_enabled
    from app.core_client import enabled as core_enabled
    if web and (not web_enabled() or not core_enabled()): raise ValueError('管理员尚未开放联网研究')
    claimed = database.session.execute(update(Conversation).where(Conversation.id == conversation.id,
        Conversation.active_run_id.is_(None)).values(active_run_id=run_id))
    if claimed.rowcount != 1:
        database.session.rollback()
        raise RunConflict('此对话正在回复，请等待完成或先停止回复')
    content = str(payload.get('content', '')).strip()
    edit_id, regenerate_id = payload.get('editMessageId'), payload.get('regenerateMessageId')
    if edit_id and regenerate_id: raise ValueError('不能同时编辑和重新回答')
    rows = database.session.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.created_at,Message.id).all()
    question = None
    assistant = None
    if regenerate_id:
        assistant = next((m for m in rows if m.id == regenerate_id and m.role == 'ASSISTANT'), None)
        if not assistant: raise ValueError('回答不存在')
        question = next((m for m in rows if m.id == assistant.parent_message_id and m.role == 'USER'), None)
        if question is None:
            question = next((m for m in reversed(rows[:rows.index(assistant)]) if m.role == 'USER'), None)
        if question is None: raise ValueError('找不到对应问题')
        content = question.content
    elif edit_id:
        original = next((m for m in rows if m.id == edit_id and m.role == 'USER'), None)
        if original is None: raise ValueError('问题不存在')
        latest = next((m for m in reversed(rows) if m.role == 'USER'), None)
        if original == latest:
            question = original
            assistant = next((m for m in rows[rows.index(original)+1:] if m.role == 'ASSISTANT'), None)
    if not content or len(content) > 8192: raise ValueError('问题不能为空且不能超过 8192 字')
    if question is None:
        question = Message(id=str(uuid.uuid4()),conversation_id=conversation.id,organization_id=user.organization_id,
                           owner_id=user.id,role='USER',content=content,status='COMPLETED')
        database.session.add(question)
        database.session.flush()
    else:
        question.content = content
        conversation.rolling_summary = ''
        conversation.summary_through_at = None
        conversation.summary_through_message_id = None
    from app.plugins.images import attach
    attach(question, payload.get('imageIds', []), user)
    if assistant is None:
        assistant = Message(id=str(uuid.uuid4()),conversation_id=conversation.id,organization_id=user.organization_id,
                            owner_id=user.id,role='ASSISTANT',content='',status='STREAMING',parent_message_id=question.id)
        database.session.add(assistant)
    else:
        database.session.query(MessageCitation).filter_by(message_id=assistant.id).delete()
        assistant.content = ''; assistant.status = 'STREAMING'; assistant.retrieval_json = None
        assistant.model = None; assistant.vote = 0; assistant.parent_message_id = question.id
        assistant.prompt_tokens = None; assistant.completion_tokens = None; assistant.latency_ms = None
    job = ChatRun(id=run_id,conversation_id=conversation.id,owner_id=user.id,user_message_id=question.id,
                  assistant_message_id=assistant.id,status='QUEUED',reasoning_enabled=reasoning,web_enabled=web)
    database.session.add(job)
    conversation.updated_at = now()
    database.session.commit()
    return job


def run_payload(job):
    return {'id':job.id,'conversationId':job.conversation_id,'userMessageId':job.user_message_id,
            'assistantMessageId':job.assistant_message_id,'status':job.status}


def execute_run(app, run_id):
    from app.chat import ChatService
    with app.app_context():
        result = database.session.execute(update(ChatRun).where(ChatRun.id==run_id,ChatRun.status=='QUEUED').values(status='RUNNING'))
        database.session.commit()
        if result.rowcount != 1: return
        job = database.session.get(ChatRun,run_id)
        conversation = database.session.get(Conversation,job.conversation_id)
        user = database.session.get(User,job.owner_id)
        question = database.session.get(Message,job.user_message_id)
        assistant = database.session.get(Message,job.assistant_message_id)
        stream = None
        last_flush = time.monotonic()
        snapshot = {'processEvents': [], 'reasoningContent': ''}
        partial = ''
        terminal = False
        cancelled = False
        failure_code = None
        failure_details = {}
        task_started = time.perf_counter()
        try:
            stream = ChatService().stream(conversation,user,question.content,job.reasoning_enabled,(question,assistant),
                                          **({'web_enabled':True} if job.web_enabled else {}))
            for block in stream:
                cancelled = database.session.execute(select(ChatRun.cancel_requested).where(ChatRun.id==run_id)).scalar()
                if cancelled:
                    stream.close()
                    break
                lines = block.splitlines()
                name = next(line[7:] for line in lines if line.startswith('event: '))
                payload = json.loads(next(line[6:] for line in lines if line.startswith('data: ')))
                database.session.add(ChatRunEvent(run_id=run_id,name=name,payload=payload))
                if name == 'delta':
                    partial += payload.get('content',''); assistant.content = partial
                elif name == 'core_run': snapshot.update(backend='core', coreRunId=payload['id'])
                elif name == 'answer_reset':
                    partial = ''; assistant.content = ''
                elif name == 'reasoning': snapshot['reasoningContent'] += payload.get('content','')
                elif name == 'progress': snapshot['processEvents'].append(payload)
                elif name == 'stock_artifact':
                    artifacts = snapshot.setdefault('stockArtifacts',[])
                    if not any(a['datasetRef']==payload['artifact']['datasetRef'] for a in artifacts): artifacts.append(payload['artifact'])
                elif name == 'retrieval': snapshot.update({k:v for k,v in (payload.get('retrieval') or {}).items() if k != 'processEvents'})
                elif name == 'model':
                    assistant.model = payload.get('model'); snapshot['reasoningEnabled'] = payload.get('reasoningEnabled')
                elif name == 'complete':
                    assistant.status='COMPLETED'; assistant.content=payload.get('content',partial)
                    job.status = 'COMPLETED'; terminal = True
                elif name == 'error':
                    job.status = 'FAILED'; terminal = True
                    failure_code = payload.get('code')
                    failure_details = {k: payload[k] for k in ('errorCategory','generationCompleted','sourceCount','invalidLabels','provider','account','model','retryable','exceptionType') if k in payload}
                if name not in ('complete','error'):
                    assistant.retrieval_json = json.dumps(snapshot,ensure_ascii=False)
                # Never hold SQLite's writer lock while waiting for the next Agent
                # event: the model node may be finalizing its audit on another thread.
                database.session.commit()
            if not terminal:
                failure_code = 'CANCELLED' if cancelled else 'STREAM_INTERRUPTED'
                job.status = 'CANCELLED' if cancelled else 'FAILED'
                assistant.status = 'FAILED'
                assistant.content = partial
                database.session.add(ChatRunEvent(run_id=run_id,name='error',payload={
                    'code':'CANCELLED' if cancelled else 'STREAM_INTERRUPTED','retryable':True}))
        except Exception as exc:
            failure_code = 'TASK_FAILED'
            failure_details = {'errorCategory': 'INTERNAL', 'exceptionType': type(exc).__name__}
            app.logger.exception('Background answer failed: %s',run_id)
            database.session.rollback()
            job = database.session.get(ChatRun,run_id)
            assistant = database.session.get(Message,job.assistant_message_id)
            job.status='FAILED'; assistant.status='FAILED'; assistant.content=partial
            database.session.add(ChatRunEvent(run_id=run_id,name='error',payload={'code':'TASK_FAILED','retryable':True}))
        finally:
            if stream: stream.close()
            job.completed_at=now()
            database.session.execute(update(Conversation).where(Conversation.id==job.conversation_id,
                Conversation.active_run_id==run_id).values(active_run_id=None,completed_run_id=run_id,updated_at=now()))
            database.session.commit()
            from app.audit import record
            if job.status == 'FAILED':
                record('exception','chat.answer_failed','FAILED', {
                    **failure_details, 'errorCode': failure_code or 'UNKNOWN',
                    'errorCategory': failure_details.get('errorCategory') or failure_code or 'UNKNOWN',
                    'conversationTitle': conversation.title, 'messageId': assistant.id,
                    'question': question.content[:4000], 'answer': assistant.content[:4000],
                    'answerLength': len(assistant.content), 'snapshotTruncated': len(assistant.content)>4000,
                    'model': assistant.model, 'lastStage': (snapshot['processEvents'][-1].get('stage') if snapshot['processEvents'] else None),
                    'recentEvents': [{k:e[k] for k in ('stage','tool','status','elapsedMsTotal','elapsedMs') if k in e} for e in snapshot['processEvents'][-12:]],
                }, int((time.perf_counter()-task_started)*1000), organization_id=user.organization_id,
                    user_id=user.id,username=user.username,conversation_id=job.conversation_id,run_id=job.id)
            record('activity','chat.run_finished',{'COMPLETED':'SUCCEEDED','CANCELLED':'CANCELLED'}.get(job.status,'FAILED'),
                {'conversationTitle':conversation.title,'errorCode':failure_code,'taskStatus':job.status},
                int((time.perf_counter()-task_started)*1000),organization_id=user.organization_id,
                user_id=user.id,username=user.username,conversation_id=job.conversation_id,run_id=job.id)


def start_worker(app):
    """One dispatcher per configured single-worker server; SQLite persists the queue."""
    lock = threading.Lock()
    started = False
    def dispatch():
        pool = ThreadPoolExecutor(max_workers=4,thread_name_prefix='chat-job')
        futures = set()
        with app.app_context():
            # Never silently regenerate partially delivered content after a process restart.
            from app.core_client import recover_interrupted_runs
            recover_interrupted_runs()
            database.session.query(AuditRecord).filter_by(status='RUNNING').update({'status':'INTERRUPTED'})
            for job in database.session.query(ChatRun).filter_by(status='RUNNING').all():
                job.status='FAILED'; job.completed_at=now()
                assistant=database.session.get(Message,job.assistant_message_id)
                if assistant: assistant.status='FAILED'
                database.session.add(ChatRunEvent(run_id=job.id,name='error',payload={'code':'WORKER_RESTARTED','retryable':True}))
                user=database.session.get(User,job.owner_id)
                question=database.session.get(Message,job.user_message_id)
                conversation=database.session.get(Conversation,job.conversation_id)
                database.session.add(AuditRecord(kind='exception',action='chat.answer_failed',status='FAILED',
                    organization_id=user.organization_id, user_id=user.id,username=user.username,
                    run_id=job.id,conversation_id=job.conversation_id,details={
                        'errorCategory':'WORKER_RESTARTED','errorCode':'WORKER_RESTARTED',
                        'conversationTitle':conversation.title if conversation else '',
                        'messageId':job.assistant_message_id,'question':question.content[:4000] if question else '',
                        'answer':assistant.content[:4000] if assistant else '',
                        'answerLength':len(assistant.content) if assistant else 0,
                        'snapshotTruncated':bool(assistant and len(assistant.content)>4000),
                        'model':assistant.model if assistant else None}))
                database.session.execute(update(Conversation).where(Conversation.active_run_id==job.id).values(
                    active_run_id=None,completed_run_id=job.id))
            database.session.commit()
        while True:
            try:
                futures={f for f in futures if not f.done()}
                with app.app_context():
                    ids=database.session.scalars(select(ChatRun.id).where(ChatRun.status=='QUEUED')
                        .order_by(ChatRun.created_at).limit(4-len(futures))).all()
                for run_id in ids: futures.add(pool.submit(execute_run,app,run_id))
            except Exception: app.logger.exception('Chat queue dispatch failed')
            time.sleep(.3)
    @app.before_request
    def ensure_worker():
        nonlocal started
        if app.testing: return
        with lock:
            if not started:
                started=True
                threading.Thread(target=dispatch,daemon=True,name='chat-dispatcher').start()
