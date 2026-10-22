"""Bounded session corpus with explicit lexical retrieval and durable promotion."""
import copy
import json
import hashlib
import math
import re
import uuid
from datetime import timedelta
from sqlalchemy import delete
from pydantic import BaseModel, Field, ConfigDict
from app.extensions import database
from app.models import now
from .models import KnowledgeSpace, KnowledgeDocument, AnalysisRun
from .security import PluginError, authorize_context


class Chunk(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=12000)
    source: dict = Field(default_factory=dict)


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=500)
    revision: str = Field(min_length=1, max_length=160)
    chunks: list[Chunk] = Field(min_length=1, max_length=1000)


def purge():
    database.session.execute(delete(KnowledgeSpace).where(KnowledgeSpace.expires_at < now()))
    database.session.execute(delete(AnalysisRun).where(AnalysisRun.expires_at < now()))
    database.session.commit()


def owned(service, sid):
    row = database.session.query(KnowledgeSpace).filter_by(id=sid, service_id=service['id'], tenant_id=service['tenantId']).first()
    if row is None or row.expires_at and row.expires_at.replace(tzinfo=now().tzinfo) <= now():
        raise PluginError('SPACE_NOT_FOUND', 404)
    authorize_context(service, row.context)
    return row


def view(space):
    return {'id': space.id, 'context': space.context, 'kind': space.kind, 'name': space.name,
            'expiresAt': space.expires_at.isoformat() if space.expires_at else None}


def create(service, body):
    context = authorize_context(service, body.get('context'))
    ttl = body.get('ttlSeconds', 3600)
    if type(ttl) is not int or not 60 <= ttl <= 86400:
        raise PluginError('INVALID_TTL')
    purge()
    count = database.session.query(KnowledgeSpace).filter_by(service_id=service['id'], tenant_id=service['tenantId'], kind='temporary').count()
    if count >= 32:
        raise PluginError('SPACE_LIMIT', 429)
    row = KnowledgeSpace(service_id=service['id'], tenant_id=service['tenantId'], context=context, expires_at=now()+timedelta(seconds=ttl))
    database.session.add(row)
    database.session.commit()
    return row


def documents(space):
    return database.session.query(KnowledgeDocument).filter_by(space_id=space.id).order_by(KnowledgeDocument.id).all()


def put(space, doc_id, body):
    if not doc_id or len(doc_id) > 160:
        raise PluginError('INVALID_DOCUMENT_ID')
    try:
        value = Document.model_validate(body).model_dump()
    except ValueError:
        raise PluginError('INVALID_DOCUMENT')
    if len({c['id'] for c in value['chunks']}) != len(value['chunks']):
        raise PluginError('DUPLICATE_CHUNK_ID')
    if any(len(json.dumps(c['source'],ensure_ascii=False).encode())>8192 for c in value['chunks']):
        raise PluginError('SOURCE_METADATA_LIMIT',413)
    if len(json.dumps(value,ensure_ascii=False).encode())>4*1024*1024:
        raise PluginError('DOCUMENT_SIZE_LIMIT',413)
    rows = documents(space)
    others = [r for r in rows if r.id != doc_id]
    if len(others) >= 100 or sum(len(c['text']) for r in others for c in r.chunks)+sum(len(c['text']) for c in value['chunks']) > 2_000_000:
        raise PluginError('CORPUS_LIMIT', 413)
    row = database.session.get(KnowledgeDocument, (space.id, doc_id))
    if row is None:
        row = KnowledgeDocument(space_id=space.id, id=doc_id)
        database.session.add(row)
    row.title, row.revision, row.chunks = value['title'], value['revision'], value['chunks']
    database.session.commit()
    return {'id': doc_id, 'chunkCount': len(row.chunks), 'revision': row.revision}


def tokens(text):
    words = re.findall(r'[a-z0-9]+|[\u3400-\u9fff]+', text.lower())
    return [part for word in words for part in ([word] if word.isascii() or len(word)==1 else [word[i:i+2] for i in range(len(word)-1)])]


def search(space, body):
    question, top_k, doc_ids = body.get('question'), body.get('topK', 8), body.get('documentIds', [])
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 8192 or type(top_k) is not int or not 1 <= top_k <= 20:
        raise PluginError('INVALID_SEARCH')
    if not isinstance(doc_ids, list) or len(doc_ids)>100 or any(not isinstance(v,str) for v in doc_ids):
        raise PluginError('INVALID_DOCUMENT_IDS')
    query = set(tokens(question))
    results = []
    for doc in documents(space):
        if doc_ids and doc.id not in doc_ids: continue
        for chunk in doc.chunks:
            terms = tokens(chunk['text'])
            if not terms: continue
            score = sum(1+math.log(terms.count(t)) for t in query if t in terms)/math.sqrt(len(terms))
            if score:
                results.append({'documentId': doc.id, 'revision': doc.revision, 'title': doc.title,
                    'chunkId': chunk['id'], 'text': chunk['text'], 'source': chunk['source'], 'score': score})
    results.sort(key=lambda r: (-r['score'], r['documentId'], r['chunkId']))
    return {'spaceId': space.id, 'mode': 'lexical', 'results': results[:top_k]}


def package(space):
    return {'contractVersion': '1', 'format': 'session-knowledge-v1', 'space': view(space),
        'documents': [{'id': d.id, 'title': d.title, 'revision': d.revision, 'chunks': d.chunks} for d in documents(space)]}


def promote(service, space, body):
    try: request_id = str(uuid.UUID(body['requestId']))
    except (KeyError, ValueError, TypeError): raise PluginError('INVALID_REQUEST_ID')
    name = body.get('name', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200: raise PluginError('INVALID_NAME')
    key = hashlib.sha256(f"{service['id']}:{service['tenantId']}:{request_id}".encode()).hexdigest()
    previous = database.session.query(KnowledgeSpace).filter_by(promotion_key=key).first()
    if previous:
        if previous.context != space.context or previous.name != name: raise PluginError('IDEMPOTENCY_CONFLICT', 409)
        return previous
    target = KnowledgeSpace(service_id=service['id'], tenant_id=service['tenantId'], context=space.context,
                            kind='persistent', name=name, expires_at=None, promotion_key=key)
    database.session.add(target)
    database.session.flush()
    for doc in documents(space):
        database.session.add(KnowledgeDocument(space_id=target.id, id=doc.id, title=doc.title, revision=doc.revision, chunks=copy.deepcopy(doc.chunks)))
    database.session.commit()
    return target
