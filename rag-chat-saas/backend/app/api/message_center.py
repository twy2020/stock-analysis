from flask import Blueprint, g, jsonify, request
from app.auth import authenticated, error
from app.admin import administrator
from app.extensions import database
from app.models import Announcement, Feedback, CenterReceipt
from app.tickets import cursor, mark_read, unread_expression

blueprint = Blueprint('message_center', __name__, url_prefix='/api/v1')


@blueprint.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def announcements():
    return database.session.query(Announcement).filter_by(organization_id=g.current_user.organization_id)


def view(item):
    read = database.session.get(CenterReceipt, (g.current_user.id, 'system', item.id))
    return dict(id=item.id, title=item.title, content=item.content, username=item.username,
                createdAt=item.created_at.isoformat(), active=item.active, unread=read is None)


@blueprint.get('/message-center/unread')
@authenticated
def unread():
    tickets = database.session.query(Feedback).filter_by(organization_id=g.current_user.organization_id, owner_id=g.current_user.id)
    return jsonify(system=announcements().filter(Announcement.active.is_(True), cursor('system', Announcement.id).is_(None)).count(),
                   feedback=tickets.filter(unread_expression()).count())


def listing(admin=False):
    page = max(1, request.args.get('page', 1, type=int))
    query = announcements()
    if not admin:
        query = query.filter_by(active=True)
    q = request.args.get('q', '').strip()[:200]
    if q:
        query = query.filter(Announcement.title.contains(q, autoescape=True))
    return jsonify(items=[view(item) for item in query.order_by(Announcement.created_at.desc(), Announcement.id).offset((page-1)*20).limit(20)],
                   total=query.count(), page=page, pageSize=20)


@blueprint.get('/announcements')
@authenticated
def user_announcements():
    return listing()


@blueprint.get('/admin/announcements')
@administrator
def admin_announcements():
    return listing(admin=True)


@blueprint.post('/admin/announcements')
@administrator
def publish():
    payload = request.get_json(silent=True) or {}
    title, content = payload.get('title'), payload.get('content')
    if not isinstance(title, str) or not isinstance(content, str) or not 1 <= len(title.strip()) <= 120 or not 1 <= len(content.strip()) <= 5000:
        return error('INVALID_REQUEST', '标题需为 1–120 字，内容需为 1–5000 字', 400)
    item = Announcement(organization_id=g.current_user.organization_id, title=title.strip(), content=content.strip(), username=g.current_user.username)
    database.session.add(item); database.session.commit()
    return jsonify(view(item)), 201


@blueprint.patch('/admin/announcements/<message_id>')
@administrator
def withdraw(message_id):
    item = announcements().filter_by(id=message_id).first()
    if not item:
        return error('NOT_FOUND', '消息不存在', 404)
    if (request.get_json(silent=True) or {}).get('active') is not False:
        return error('INVALID_REQUEST', '仅支持撤回已发布消息', 400)
    item.active = False
    database.session.commit()
    return jsonify(view(item))


@blueprint.post('/announcements/<message_id>/read')
@authenticated
def mark_announcement_read(message_id):
    if not announcements().filter_by(id=message_id, active=True).first():
        return error('NOT_FOUND', '消息不存在或已撤回', 404)
    mark_read('system', message_id, 1)
    return '', 204
