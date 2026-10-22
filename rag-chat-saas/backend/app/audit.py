"""Diagnostic snapshots contain no credentials, headers or raw provider responses."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
from flask import current_app, has_app_context, g, request
from app.extensions import database
from app.models import AuditRecord, Conversation, Message, User, AiAccount, AiProvider, Feedback, ChatRun

context = ContextVar('audit_context', default={})


@contextmanager
def call_context(**values):
    token = context.set(values)
    try:
        yield
    finally:
        context.reset(token)


def record(kind, action, status, details=None, latency_ms=None, record_id=None, **identity):
    if not has_app_context(): return None
    values = {**context.get(), **identity}
    try:
        # The stream worker may already hold SQLite's write transaction for partial
        # tokens. Use that same scoped session instead of deadlocking a second writer.
        session=database.session
        row = session.get(AuditRecord, record_id) if record_id else None
        if row is None:
            row = AuditRecord(kind=kind, action=action, **{k:v for k,v in values.items() if k in {
                'organization_id','user_id','username','run_id','conversation_id'}})
            session.add(row)
        row.status=status; row.latency_ms=latency_ms; row.details=details or {}
        session.commit()
        return row.id
    except Exception:
        database.session.rollback()
        current_app.logger.exception('Audit record could not be saved')
        return None


def install_activity_audit(app):
    @app.before_request
    def capture():
        if request.method not in {'POST','PUT','PATCH','DELETE'}: return
        endpoint = request.endpoint or ''
        if not endpoint.startswith(('auth.','admin.','conversations.','chat.','feedback.','message_center.')): return
        if endpoint.endswith(('mark_read','mark_announcement_read','discover_provider_models')): return
        user = getattr(g, 'current_user', None)
        payload = request.get_json(silent=True) or {}
        details = {}
        # Explicit allowlist: never persist password, API key, request headers or arbitrary JSON.
        for key in ('status','role','concurrencyLimit','weight','vote','inviteRequired'):
            if key in payload: details[key] = payload[key]
        if endpoint == 'admin.put_registration_settings':
            details['inviteCodeChanged'] = bool(payload.get('inviteCode'))
        for key in ('username','name','title','model'):
            if key in payload: details[key] = str(payload[key])[:200]
        args=request.view_args or {}
        if endpoint.startswith('feedback.') and args.get('feedback_id'):
            target = database.session.get(Feedback, args['feedback_id'])
            if target and user and target.organization_id == user.organization_id and (target.owner_id == user.id or user.role == 'ADMIN'):
                details.update(feedbackId=target.id, target=target.username, previousStatus=target.status)
                if isinstance(payload.get('body'), str): details['replyLength'] = len(payload['body'])
        if endpoint.startswith('message_center.'):
            details['messageId'] = args.get('message_id')
        for key,model in [('account_id',AiAccount),('provider_id',AiProvider),('user_id',User)]:
            if args.get(key) and user and user.role=='ADMIN':
                target=database.session.get(model,args[key])
                if target:
                    details['target']=getattr(target,'name',None) or getattr(target,'username','')
                    details['changes']={}
                    for field,attr in [('status','status'),('role','role'),('concurrencyLimit','concurrency_limit'),('weight','weight'),('model','model'),('name','name')]:
                        if field in payload and hasattr(target,attr):details['changes'][field]={'before':getattr(target,attr),'after':payload[field]}
        cid=args.get('conversation_id') or request.form.get('conversationId')
        conversation=database.session.get(Conversation,cid) if cid else None
        if conversation and user and conversation.owner_id==user.id:
            details['conversationTitle']=conversation.title
        mid=args.get('message_id')
        message=database.session.get(Message,mid) if mid else None
        if message and user and message.owner_id==user.id:
            details.update(messageId=mid,answer=message.content[:4000],previousVote=message.vote)
            question=database.session.get(Message,message.parent_message_id) if message.parent_message_id else None
            if question: details['question']=question.content[:2000]
            run=database.session.query(ChatRun).filter_by(assistant_message_id=mid).order_by(ChatRun.created_at.desc()).first()
            if run: details['taskId']=run.id
        if payload.get('editMessageId'): details['operation']='编辑问题'
        if payload.get('regenerateMessageId'): details['operation']='重新回答'
        g.audit_capture = dict(start=time.perf_counter(),action=endpoint,details=details,
            organization_id=user.organization_id if user else None,user_id=user.id if user else None,
            username=user.username if user else str(payload.get('username') or '未登录')[:80],conversation_id=cid)

    @app.after_request
    def save(response):
        capture=getattr(g,'audit_capture',None)
        if not capture: return response
        values=dict(capture); started=values.pop('start'); details=values.pop('details'); action=values.pop('action')
        data=response.get_json(silent=True) if response.is_json else None
        if isinstance(data,dict):
            if action=='chat.create_run': details['taskId']=data.get('id')
            if action=='feedback.create_feedback':
                details['feedbackId']=data.get('id')
                feedback=database.session.get(Feedback,data.get('id')) if data.get('id') else None
                if feedback:details.update(comment=feedback.comment,imageCount=len(feedback.images),conversationTitle=feedback.conversation_title)
            if data.get('code'): details['errorCode']=data['code']
        if action in {'auth.login', 'auth.register'} and not values['organization_id']:
            user=database.session.query(User).filter_by(username=values['username'].strip().lower()).first()
            if user: values.update(organization_id=user.organization_id,user_id=user.id)
        details['httpStatus']=response.status_code
        values['run_id']=details.get('taskId') or (request.view_args or {}).get('run_id')
        record('activity',action,'SUCCEEDED' if response.status_code<400 else 'FAILED',details,
               int((time.perf_counter()-started)*1000),**values)
        return response
