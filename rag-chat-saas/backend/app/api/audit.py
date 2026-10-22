from datetime import datetime, timezone
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, or_, cast, String
from app.admin import administrator
from app.auth import error
from app.extensions import database
from app.models import AuditRecord

blueprint=Blueprint('audit',__name__,url_prefix='/api/v1/admin/audit')


def filtered():
    query=database.session.query(AuditRecord).filter(AuditRecord.organization_id==g.current_user.organization_id)
    kind=request.args.get('kind','model')
    if kind not in {'model','activity','tool','exception'}: raise ValueError('日志类型无效')
    query=query.filter_by(kind=kind)
    for key in ('status','action','run_id','conversation_id'):
        value=request.args.get(key)
        if value: query=query.filter(getattr(AuditRecord,key)==value[:100])
    q=request.args.get('q','').strip()[:200]
    if q:
        query=query.filter(or_(AuditRecord.username.contains(q,autoescape=True),
            cast(AuditRecord.details,String).contains(q,autoescape=True)))
    for key, operator in [('from',AuditRecord.created_at.__ge__),('to',AuditRecord.created_at.__le__)]:
        value=request.args.get(key)
        if value:
            date=datetime.fromisoformat(value.replace('Z','+00:00'))
            if date.tzinfo: date=date.astimezone(timezone.utc).replace(tzinfo=None)
            query=query.filter(operator(date))
    if request.args.get('rotated')=='true': query=query.filter(AuditRecord.details['rotated'].as_boolean()==True)
    return query


@blueprint.get('')
@administrator
def list_audit():
    try:
        page=max(1,int(request.args.get('page','1')))
        query=filtered()
    except (ValueError,TypeError): return error('INVALID_REQUEST','筛选条件无效',400)
    total=query.count()
    counts=dict(query.with_entities(AuditRecord.status,func.count()).group_by(AuditRecord.status).all())
    average=query.with_entities(func.avg(AuditRecord.latency_ms)).scalar()
    items=query.order_by(AuditRecord.created_at.desc(),AuditRecord.id).offset((page-1)*30).limit(30).all()
    return jsonify(items=[dict(id=r.id,kind=r.kind,action=r.action,status=r.status,username=r.username,
        runId=r.run_id,conversationId=r.conversation_id,latencyMs=r.latency_ms,details=r.details,
        createdAt=r.created_at.isoformat()+'Z') for r in items],total=total,page=page,pageSize=30,
        summary={'counts':counts,'averageMs':round(average or 0)})
