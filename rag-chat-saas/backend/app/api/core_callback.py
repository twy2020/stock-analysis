"""Core may query only the knowledge base bound to the delegated conversation."""
import hashlib
import hmac
from urllib.parse import quote

from flask import Blueprint, current_app, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.extensions import database
from app.features import rag_enabled
from app.models import Conversation, User
from app.clients.rag import RagClient, RagClientError

blueprint = Blueprint('core_callback', __name__, url_prefix='/api/internal/agent-core')


class DirectoryArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    offset: int = Field(default=0, ge=0, le=1000000)
    limit: int = Field(default=100, ge=1, le=100)


class RecallArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question: str = Field(min_length=1, max_length=8192)
    documentIds: list[str] = Field(default_factory=list, max_length=50)
    topK: int = Field(default=8, ge=1, le=20)


@blueprint.post('/rag')
def rag():
    if not rag_enabled(): return {'code':'RAG_DISABLED'},403
    if request.headers.get('Origin'): return {'code':'SERVICE_ONLY'}, 403
    header = request.headers.get('Authorization', '')
    token = header[7:] if header.startswith('Bearer ') else ''
    expected = current_app.config.get('AGENT_CORE_CALLBACK_TOKEN_SHA256', '')
    if not token or not expected or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected):
        return {'code':'AUTHENTICATION_REQUIRED'}, 401
    request.max_content_length = 64*1024
    body = request.get_json(silent=True) or {}
    context = body.get('context')
    if not isinstance(context, dict): return {'code':'INVALID_CONTEXT'}, 400
    user = database.session.get(User, context.get('actor_id')) if context.get('actor_id') else None
    row = database.session.get(Conversation, context.get('conversation_id')) if context.get('conversation_id') else None
    if not user or user.status != 'ACTIVE' or not row or row.owner_id != user.id or row.organization_id != user.organization_id \
            or context.get('tenant_id') != row.organization_id or context.get('knowledge_base_id') != row.knowledge_base_id:
        return {'code':'CONTEXT_FORBIDDEN'}, 403
    if not row.knowledge_base_id: return {'code':'KNOWLEDGE_BASE_REQUIRED'}, 400
    path = '/api/v1/consumer/knowledge-bases/' + quote(row.knowledge_base_id, safe='')
    try:
        if body.get('operation') == 'list_documents':
            args = DirectoryArgs.model_validate(body.get('arguments')).model_dump()
            return RagClient().json('POST', path+'/tools/execute', {'operation':'list_documents','arguments':args})
        if body.get('operation') == 'recall':
            args = RecallArgs.model_validate(body.get('arguments')).model_dump()
            result = None
            for name, payload in RagClient().retrieve_stream(path+'/retrieve', {**args, 'mode':'hybrid'}):
                if name == 'retrieval': result = payload
            if result is None: raise RagClientError()
            return result
        return {'code':'TOOL_FORBIDDEN'}, 403
    except ValidationError:
        return {'code':'INVALID_ARGUMENTS'}, 400
    except RagClientError:
        return {'code':'RAG_UNAVAILABLE'}, 503
