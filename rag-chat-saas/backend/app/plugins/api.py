import json
import time
import threading
from flask import Blueprint, g, request, jsonify, Response, stream_with_context, current_app
from werkzeug.exceptions import RequestEntityTooLarge
from app.extensions import database
from app.audit import record
from .security import require_service, authorize_context, PluginError
from . import knowledge, registry
from .models import KnowledgeDocument, AnalysisEvent

blueprint = Blueprint('service_plugins', __name__, url_prefix='/api/service/v1')
mutation_lock = threading.RLock()


@blueprint.errorhandler(PluginError)
def plugin_error(exc):
    database.session.rollback()
    return jsonify({'code': exc.code, 'message': exc.message, 'retryable': exc.status in (429,502,503)}), exc.status


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict): raise PluginError('INVALID_REQUEST')
    return value


def version(value):
    if value.get('contractVersion', '1') != '1': raise PluginError('UNSUPPORTED_CONTRACT_VERSION')


@blueprint.get('/capabilities')
@require_service
def capabilities():
    return jsonify({'contractVersion': '1', 'tools': [
        {k:v for k,v in item.items() if k in ('name','version','description','effect','inputSchema','outputSchema')}
        for item in registry.catalog(g.plugin_service).values()]})


@blueprint.post('/tools/execute')
@require_service
def execute():
    value = body(); version(value)
    context = authorize_context(g.plugin_service, value.get('context'))
    return jsonify(registry.execute(g.plugin_service, context, value.get('tool'), value.get('arguments'), value.get('requestId')))


@blueprint.post('/spaces')
@require_service
def create_space():
    with mutation_lock:
        return jsonify(knowledge.view(knowledge.create(g.plugin_service, body()))), 201


@blueprint.get('/spaces/<sid>')
@require_service
def space(sid):
    value = knowledge.owned(g.plugin_service, sid)
    return jsonify({**knowledge.view(value), 'documents': [
        {'id': d.id, 'title': d.title, 'revision': d.revision, 'chunkCount': len(d.chunks)} for d in knowledge.documents(value)]})


@blueprint.delete('/spaces/<sid>')
@require_service
def delete_space(sid):
    with mutation_lock:
        row = knowledge.owned(g.plugin_service, sid)
        database.session.delete(row); database.session.commit()
        record('tool', 'session.delete_space', 'SUCCEEDED', {'spaceId': sid, 'serviceId': g.plugin_service['id']})
        return '', 204


@blueprint.put('/spaces/<sid>/documents/<doc_id>')
@require_service
def put_document(sid, doc_id):
    with mutation_lock:
        result = knowledge.put(knowledge.owned(g.plugin_service,sid), doc_id, body())
        record('tool','session.load_document','SUCCEEDED',{'spaceId':sid,'documentId':doc_id})
        return jsonify(result)


@blueprint.delete('/spaces/<sid>/documents/<doc_id>')
@require_service
def delete_document(sid, doc_id):
    with mutation_lock:
        knowledge.owned(g.plugin_service,sid)
        database.session.query(KnowledgeDocument).filter_by(space_id=sid,id=doc_id).delete()
        database.session.commit()
        record('tool','session.unload_document','SUCCEEDED',{'spaceId':sid,'documentId':doc_id})
        return '', 204


@blueprint.post('/spaces/<sid>/search')
@require_service
def search(sid):
    return jsonify(knowledge.search(knowledge.owned(g.plugin_service,sid),body()))


@blueprint.get('/spaces/<sid>/package')
@require_service
def package(sid):
    return jsonify(knowledge.package(knowledge.owned(g.plugin_service,sid)))


@blueprint.post('/spaces/<sid>/promote')
@require_service
def promote(sid):
    with mutation_lock:
        result = knowledge.promote(g.plugin_service, knowledge.owned(g.plugin_service,sid), body())
        record('tool','session.promote','SUCCEEDED',{'spaceId':sid,'persistentSpaceId':result.id,'serviceId':g.plugin_service['id']})
        return jsonify(knowledge.view(result)), 201


@blueprint.post('/runs')
@require_service
def create_run():
    from .runs import enqueue, view
    with mutation_lock:
        value = body(); version(value)
        return jsonify(view(enqueue(g.plugin_service,value))), 202


@blueprint.get('/runs/<rid>')
@require_service
def get_run(rid):
    from .runs import owned, view
    return jsonify(view(owned(g.plugin_service,rid)))


@blueprint.post('/runs/<rid>/cancel')
@require_service
def cancel_run(rid):
    from .runs import owned, view, append_event
    with mutation_lock:
        row = owned(g.plugin_service,rid)
        row.cancel_requested = True
        if row.status == 'QUEUED':
            from app.models import now
            row.status = 'CANCELLED'
            row.payload = {}
            row.completed_at = now()
            append_event(row,'error',{'code':'CANCELLED','retryable':False})
        database.session.commit()
        return jsonify(view(row))


@blueprint.get('/runs/<rid>/events')
@require_service
def events(rid):
    from .runs import owned
    service = dict(g.plugin_service)
    owned(service,rid)
    try: cursor = max(0,int(request.args.get('after', request.headers.get('Last-Event-ID','0'))))
    except ValueError: raise PluginError('INVALID_EVENT_CURSOR')
    def stream():
        nonlocal cursor
        last_ping = 0
        while True:
            try: run = owned(service,rid)
            except PluginError:
                yield 'event: error\ndata: {"code":"RUN_EXPIRED"}\n\n'; return
            rows = database.session.query(AnalysisEvent).filter(AnalysisEvent.run_id==rid,AnalysisEvent.id>cursor).order_by(AnalysisEvent.id).limit(200).all()
            status = run.status
            data = [(r.id,r.name,r.payload) for r in rows]
            database.session.remove()
            for sequence,name,payload in data:
                cursor=sequence
                yield f'id: {sequence}\nevent: {name}\ndata: '+json.dumps({**payload,'eventId':sequence},ensure_ascii=False)+'\n\n'
            if not data and status not in ('QUEUED','RUNNING'): return
            if time.monotonic()-last_ping>10:
                yield ': keepalive\n\n'; last_ping=time.monotonic()
            time.sleep(.1)
    return Response(stream_with_context(stream()),mimetype='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
