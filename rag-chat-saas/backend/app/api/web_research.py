"""Core-only web adapter, bound to a user-owned run that opted in."""
import hmac
from pathlib import Path
from threading import BoundedSemaphore
from flask import Blueprint, current_app, request
from jsonschema import Draft202012Validator
from app.extensions import database
from app.features import web_enabled
from app.models import Conversation, ChatRun, User
from app.web_contract import TOOLS
from app.web_research import execute, WEB_ERRORS

blueprint=Blueprint('web_research',__name__,url_prefix='/api/internal/stock-web')
slots=BoundedSemaphore(2)


@blueprint.post('/execute')
def execute_tool():
    if request.headers.get('Origin'):return {'code':'SERVICE_ONLY'},403
    try:token=Path(current_app.config['STOCK_ENGINE_TOKEN_FILE']).read_text().strip()
    except (OSError,KeyError):return {'code':'WEB_NOT_CONFIGURED'},503
    if not token or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):
        return {'code':'AUTHENTICATION_REQUIRED'},401
    if not web_enabled():return {'code':'WEB_DISABLED'},403
    request.max_content_length=32*1024
    body=request.get_json(silent=True) or {}; context=body.get('context',{})
    if not isinstance(context,dict):return {'code':'INVALID_CONTEXT'},400
    user=database.session.get(User,context.get('actor_id'))
    conversation=database.session.get(Conversation,context.get('conversation_id'))
    if not user or user.status!='ACTIVE' or not conversation or conversation.owner_id!=user.id or conversation.organization_id!=user.organization_id or context.get('tenant_id')!=user.organization_id:
        return {'code':'CONTEXT_FORBIDDEN'},403
    job=database.session.get(ChatRun,conversation.active_run_id) if conversation.active_run_id else None
    if not job or not job.web_enabled or job.owner_id!=user.id or job.status!='RUNNING' or job.cancel_requested:
        return {'code':'WEB_RUN_FORBIDDEN'},403
    entry=next((t for t in TOOLS if t['name']==body.get('tool')),None)
    if not entry or list(Draft202012Validator(entry['inputSchema']).iter_errors(body.get('arguments'))):
        return {'code':'INVALID_WEB_ARGUMENTS'},400
    if not slots.acquire(blocking=False):return {'code':'WEB_BUSY'},429
    try:
        result=execute(entry['name'],body['arguments'],{k:context[k] for k in ('actor_id','tenant_id','conversation_id')},
                       str(Path(current_app.config['DATABASE_PATH']).parent/'stock-web'))
        return {'contractVersion':'1','status':'succeeded','data':result}
    except ValueError as exc:
        return {'contractVersion':'1','status':'failed','error':str(exc) if str(exc) in WEB_ERRORS else 'WEB_RESEARCH_UNAVAILABLE',
                'retryable':False,**({'data':exc.details} if hasattr(exc,'details') else {})},200
    except Exception:
        # Upstream diagnostics may include page text or environment credentials.
        return {'contractVersion':'1','status':'failed','error':'WEB_RESEARCH_UNAVAILABLE'},200
    finally:slots.release()
