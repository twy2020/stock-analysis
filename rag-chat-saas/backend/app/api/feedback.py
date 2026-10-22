from __future__ import annotations

import io
import json
import warnings

from flask import Blueprint, g, jsonify, request, send_file
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from sqlalchemy import func, or_, select, update

from app.admin import administrator
from app.auth import authenticated, error
from app.api.conversations import owned_conversation
from app.extensions import database
from app.models import Feedback, FeedbackImage, FeedbackReply
from app.tickets import ticket_summary, ticket_detail, latest_id, mark_read, add_reply, unread_expression

blueprint = Blueprint('feedback', __name__, url_prefix='/api/v1')
STATUSES = {'NEW', 'REVIEWING', 'RESOLVED'}


@blueprint.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def summary(item):
    return ticket_summary(item, admin=True)


def clean_snapshot(raw):
    if len(raw.encode('utf-8')) > 1024 * 1024:
        raise ValueError('对话快照过大，请缩短后重试')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('对话快照格式无效')
    messages = value.get('messages', [])
    if not isinstance(messages, list) or len(messages) > 200:
        raise ValueError('最多记录最近 200 条消息')
    cleaned = []
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in {'USER', 'ASSISTANT'}:
            raise ValueError('消息格式无效')
        content = message.get('content', '')
        if not isinstance(content, str) or len(content) > 100000:
            raise ValueError('消息内容过长')
        cleaned.append({'role': message['role'], 'content': content,
                        'status': str(message.get('status', ''))[:30],
                        'model': str(message.get('model') or '')[:200]})
    return {'messages': cleaned, 'draft': str(value.get('draft', ''))[:8192],
            'error': str(value.get('error', ''))[:2000],
            'knowledgeBase': str(value.get('knowledgeBase', ''))[:500],
            'capturedAt': str(value.get('capturedAt', ''))[:40],
            'truncated': bool(value.get('truncated', False))}


@blueprint.post('/feedback')
@authenticated
def create_feedback():
    request.max_content_length = 17 * 1024 * 1024
    request.max_form_memory_size = 2 * 1024 * 1024
    try:
        comment = request.form.get('comment', '').strip()
        if not comment or len(comment) > 5000:
            return error('INVALID_REQUEST', '请填写 1–5000 字的反馈意见', 400)
        conversation_id = request.form.get('conversationId', '').strip() or None
        conversation = owned_conversation(conversation_id) if conversation_id else None
        if conversation_id and conversation is None:
            return error('NOT_FOUND', '对话不存在或无权访问', 404)
        snapshot = clean_snapshot(request.form.get('snapshot', '{}'))
        files = request.files.getlist('images')
        if len(files) > 3:
            return error('INVALID_REQUEST', '最多上传 3 张图片', 400)
        images = []
        for upload in files:
            data = upload.read(5 * 1024 * 1024 + 1)
            if len(data) > 5 * 1024 * 1024:
                return error('INVALID_REQUEST', '每张图片不能超过 5 MB', 400)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format not in {'PNG', 'JPEG', 'WEBP'} or image.width * image.height > 20000000:
                        raise ValueError('仅支持 PNG、JPEG、WebP 图片，像素总数不能超过 2000 万')
                    image.load()
                    # Re-encode to discard metadata and any trailing active content.
                    output = io.BytesIO()
                    image.convert('RGB').save(output, format='PNG')
                    normalized = output.getvalue()
                    if len(normalized) > 10 * 1024 * 1024:
                        raise ValueError('图片解码后过大，请压缩后上传')
                    images.append(FeedbackImage(name=str(upload.filename or '图片')[:200], media_type='image/png', data=normalized))
        item = Feedback(organization_id=g.current_user.organization_id, owner_id=g.current_user.id,
                        username=g.current_user.username, conversation_id=conversation_id,
                        conversation_title=conversation.title if conversation else '新对话',
                        comment=comment, snapshot=snapshot, images=images)
        database.session.add(item)
        database.session.commit()
        return jsonify(ticket_summary(item)), 201
    except RequestEntityTooLarge:
        return error('UPLOAD_TOO_LARGE', '上传内容过大，最多 3 张图片，每张不超过 5 MB', 413)
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        return error('INVALID_REQUEST', '图片或对话快照无效，请检查格式和大小后重试', 400)


def scoped_feedback(feedback_id):
    return database.session.query(Feedback).filter_by(id=feedback_id, organization_id=g.current_user.organization_id).one_or_none()


@blueprint.get('/admin/feedback')
@administrator
def list_feedback():
    return feedback_listing(admin=True)


def feedback_listing(admin=False):
    page = max(1, request.args.get('page', 1, type=int))
    status = request.args.get('status', '')
    query = database.session.query(Feedback).filter_by(organization_id=g.current_user.organization_id)
    if not admin:
        query = query.filter_by(owner_id=g.current_user.id)
    search = request.args.get('q', '').strip()[:200]
    if search:
        query = query.filter(or_(Feedback.comment.contains(search, autoescape=True), Feedback.username.contains(search, autoescape=True),
                                 Feedback.id.contains(search.removeprefix('FB-').split('-')[-1].lower(), autoescape=True)))
    if request.args.get('unread') == 'true':
        query = query.filter(unread_expression(admin))
    if status:
        if status not in STATUSES:
            return error('INVALID_REQUEST', '反馈状态无效', 400)
        query = query.filter_by(status=status)
    total = query.count()
    updated = select(func.max(FeedbackReply.created_at)).where(FeedbackReply.feedback_id == Feedback.id).correlate(Feedback).scalar_subquery()
    items = query.order_by(func.coalesce(updated, Feedback.created_at).desc(), Feedback.id).offset((page - 1) * 20).limit(20).all()
    return jsonify(items=[ticket_summary(item, admin) for item in items], total=total, page=page, pageSize=20)


@blueprint.get('/admin/feedback/<feedback_id>')
@administrator
def get_feedback(feedback_id):
    item = scoped_feedback(feedback_id)
    if item is None:
        return error('NOT_FOUND', '反馈不存在', 404)
    return jsonify(ticket_summary(item, True) if request.args.get('summary') == 'true' else ticket_detail(item, admin=True))


@blueprint.patch('/admin/feedback/<feedback_id>')
@administrator
def update_feedback(feedback_id):
    item = scoped_feedback(feedback_id)
    if item is None:
        return error('NOT_FOUND', '反馈不存在', 404)
    status = (request.get_json(silent=True) or {}).get('status')
    if status not in STATUSES:
        return error('INVALID_REQUEST', '反馈状态无效', 400)
    previous = item.status
    changed = database.session.execute(update(Feedback).where(Feedback.id == item.id, Feedback.status == previous).values(status=status)).rowcount
    if not changed:
        database.session.rollback()
        return error('CONFLICT', '工单已更新，请刷新后重试', 409)
    if previous != status:
        labels = {'NEW':'已重新开启工单', 'REVIEWING':'工单正在处理', 'RESOLVED':'管理员已关闭工单'}
        add_reply(item, labels[status], kind='STATUS', admin=True)
    database.session.commit()
    return jsonify(summary(item))


@blueprint.get('/admin/feedback/<feedback_id>/images/<image_id>')
@administrator
def get_feedback_image(feedback_id, image_id):
    if scoped_feedback(feedback_id) is None:
        return error('NOT_FOUND', '反馈不存在', 404)
    image = database.session.query(FeedbackImage).filter_by(id=image_id, feedback_id=feedback_id).one_or_none()
    if image is None:
        return error('NOT_FOUND', '图片不存在', 404)
    response = send_file(io.BytesIO(image.data), mimetype=image.media_type, download_name='feedback.png')
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def owned_feedback(feedback_id):
    item = scoped_feedback(feedback_id)
    return item if item and item.owner_id == g.current_user.id else None


@blueprint.get('/feedback')
@authenticated
def user_feedback():
    return feedback_listing()


@blueprint.get('/feedback/<feedback_id>')
@authenticated
def user_feedback_detail(feedback_id):
    item = owned_feedback(feedback_id)
    return jsonify(ticket_summary(item) if request.args.get('summary') == 'true' else ticket_detail(item)) if item else error('NOT_FOUND', '工单不存在', 404)


def reply_to_ticket(feedback_id, admin=False):
    item = scoped_feedback(feedback_id) if admin else owned_feedback(feedback_id)
    if not item:
        return error('NOT_FOUND', '工单不存在', 404)
    body = (request.get_json(silent=True) or {}).get('body')
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 5000:
        return error('INVALID_REQUEST', '请填写 1–5000 字的回复', 400)
    # Acquire the write lock and recheck closure atomically, including SQLite.
    changed = database.session.execute(update(Feedback).where(Feedback.id == item.id, Feedback.status != 'RESOLVED')
        .values(status='REVIEWING' if admin else 'NEW')).rowcount
    if not changed:
        database.session.rollback()
        return error('TICKET_CLOSED', '工单已关闭，不能继续回复', 409)
    add_reply(item, body.strip(), admin=admin)
    database.session.commit()
    return jsonify(ticket_detail(item, admin)), 201


@blueprint.post('/feedback/<feedback_id>/replies')
@authenticated
def user_reply(feedback_id):
    return reply_to_ticket(feedback_id)


@blueprint.post('/admin/feedback/<feedback_id>/replies')
@administrator
def admin_reply(feedback_id):
    return reply_to_ticket(feedback_id, admin=True)


def read_ticket(feedback_id, admin=False):
    item = scoped_feedback(feedback_id) if admin else owned_feedback(feedback_id)
    if not item:
        return error('NOT_FOUND', '工单不存在', 404)
    through = (request.get_json(silent=True) or {}).get('through')
    if type(through) is not int or not 0 <= through <= latest_id(item.id):
        return error('INVALID_REQUEST', '已读位置无效', 400)
    mark_read('feedback', item.id, through)
    return '', 204


@blueprint.post('/feedback/<feedback_id>/read')
@authenticated
def user_mark_read(feedback_id):
    return read_ticket(feedback_id)


@blueprint.post('/admin/feedback/<feedback_id>/read')
@administrator
def admin_mark_read(feedback_id):
    return read_ticket(feedback_id, admin=True)


@blueprint.get('/feedback/<feedback_id>/images/<image_id>')
@authenticated
def user_feedback_image(feedback_id, image_id):
    if not owned_feedback(feedback_id):
        return error('NOT_FOUND', '工单不存在', 404)
    image = database.session.query(FeedbackImage).filter_by(id=image_id, feedback_id=feedback_id).one_or_none()
    if not image:
        return error('NOT_FOUND', '图片不存在', 404)
    response = send_file(io.BytesIO(image.data), mimetype=image.media_type, download_name='feedback.png')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@blueprint.get('/admin/feedback/stats')
@administrator
def feedback_stats():
    query = database.session.query(Feedback).filter_by(organization_id=g.current_user.organization_id)
    return jsonify(total=query.count(), new=query.filter_by(status='NEW').count(),
        reviewing=query.filter_by(status='REVIEWING').count(), closed=query.filter_by(status='RESOLVED').count(),
        unread=query.filter(unread_expression(True)).count())
