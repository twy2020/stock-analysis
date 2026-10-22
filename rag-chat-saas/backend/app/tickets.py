"""Ticket queries and per-user read cursors; original feedback remains intact."""
from flask import g
from sqlalchemy import select, func, or_
from sqlalchemy.dialects.sqlite import insert
from app.extensions import database
from app.models import Feedback, FeedbackReply, CenterReceipt


def cursor(kind, item_id):
    return select(CenterReceipt.through).where(CenterReceipt.user_id == g.current_user.id,
        CenterReceipt.kind == kind, CenterReceipt.item_id == item_id).correlate_except(CenterReceipt).scalar_subquery()


def unread_expression(admin=False):
    seen = cursor('feedback', Feedback.id)
    incoming = select(FeedbackReply.id).where(FeedbackReply.feedback_id == Feedback.id,
        FeedbackReply.author_role == ('USER' if admin else 'ADMIN'),
        FeedbackReply.id > func.coalesce(seen, 0)).exists()
    return or_(seen.is_(None), incoming) if admin else incoming


def latest_id(feedback_id):
    return database.session.query(func.max(FeedbackReply.id)).filter_by(feedback_id=feedback_id).scalar() or 0


def mark_read(kind, item_id, through):
    stmt = insert(CenterReceipt).values(user_id=g.current_user.id, kind=kind, item_id=item_id, through=through)
    database.session.execute(stmt.on_conflict_do_update(index_elements=['user_id', 'kind', 'item_id'],
        set_={'through': func.max(CenterReceipt.through, through)}))
    database.session.commit()


def add_reply(item, body, kind='REPLY', admin=False):
    reply = FeedbackReply(feedback_id=item.id, author_id=g.current_user.id, username=g.current_user.username,
        author_role='ADMIN' if admin else 'USER', body=body, kind=kind)
    database.session.add(reply)
    return reply


def ticket_summary(item, admin=False):
    latest = database.session.query(FeedbackReply).filter_by(feedback_id=item.id).order_by(FeedbackReply.id.desc()).first()
    unread = database.session.query(Feedback.id).filter(Feedback.id == item.id, unread_expression(admin)).first() is not None
    return dict(id=item.id, ticketNumber='FB-' + item.created_at.strftime('%Y%m%d') + '-' + item.id[:8].upper(),
        username=item.username, comment=item.comment, conversationTitle=item.conversation_title, status=item.status,
        createdAt=item.created_at.isoformat(), updatedAt=(latest.created_at if latest else item.created_at).isoformat(),
        latestPreview=latest.body if latest else item.comment, latestReplyId=latest.id if latest else 0,
        imageCount=len(item.images), unread=unread)


def ticket_detail(item, admin=False):
    replies = database.session.query(FeedbackReply).filter_by(feedback_id=item.id).order_by(FeedbackReply.id).all()
    prefix = '/api/v1/admin/feedback' if admin else '/api/v1/feedback'
    values = ticket_summary(item, admin)
    values['latestReplyId'] = replies[-1].id if replies else 0
    return dict(**values, snapshot=item.snapshot, images=[
        {'id':img.id, 'name':img.name, 'url':f'{prefix}/{item.id}/images/{img.id}'} for img in item.images],
        replies=[dict(id=r.id, username=r.username, role=r.author_role, body=r.body, kind=r.kind,
                      createdAt=r.created_at.isoformat()) for r in replies])
