from __future__ import annotations

from app.extensions import database
from app.models import Conversation, Message



SUMMARY_MAX_CHARS = 4000


def _summary_line(message: Message) -> str:
    role = "用户" if message.role == "USER" else "助手"
    content = " ".join((message.content or "").split())
    return f"{role}：{content[:600]}"


def compact_conversation(conversation: Conversation, *, keep_recent: int = 8,
                         compact_after: int = 12) -> bool:
    history = database.session.query(Message).filter_by(
        conversation_id=conversation.id,
        owner_id=conversation.owner_id,
        status="COMPLETED",
    ).order_by(Message.created_at.asc(), Message.id.asc()).all()
    if len(history) <= compact_after:
        return False
    eligible = history[:-keep_recent] if keep_recent else history
    if conversation.summary_through_message_id:
        cursor = next((index for index, item in enumerate(eligible)
                       if item.id == conversation.summary_through_message_id), None)
        if cursor is not None:
            eligible = eligible[cursor + 1:]
    if not eligible:
        return False
    additions = "\n".join(_summary_line(item) for item in eligible)
    merged = "\n".join(value for value in (conversation.rolling_summary, additions) if value)
    conversation.rolling_summary = merged[-SUMMARY_MAX_CHARS:]
    conversation.summary_through_message_id = eligible[-1].id
    conversation.summary_through_at = eligible[-1].created_at
    return True


def build_messages(conversation: Conversation, question: str, retrieval: dict | None,
                   exclude_message_id: str | None = None) -> list[dict]:
    from app.plugins.images import message_content
    query = database.session.query(Message).filter_by(
        conversation_id=conversation.id, owner_id=conversation.owner_id, status="COMPLETED"
    )
    if conversation.summary_through_at:
        query = query.filter(Message.created_at > conversation.summary_through_at)
    if exclude_message_id:
        query = query.filter(Message.id != exclude_message_id)
        target = database.session.get(Message, exclude_message_id)
        if target: query = query.filter(Message.created_at < target.created_at)
    history = query.order_by(Message.created_at.desc()).limit(12).all()
    from app.stock import PROMPT
    messages = [{"role": "system", "content": PROMPT}]
    if conversation.rolling_summary:
        messages.append({"role": "system", "content": f"历史摘要：{conversation.rolling_summary}"})
    for item in reversed(history):
        messages.append({"role": item.role.lower(), "content": message_content(item) if item.role == 'USER' else item.content})
        if item.role == 'ASSISTANT' and item.retrieval_json:
            import json
            artifacts = json.loads(item.retrieval_json).get('stockArtifacts',[])
            if artifacts:
                messages.append({'role':'system','content':'历史数据集引用（数值需用stock_dataset在本轮复核）：'+json.dumps(
                    [{'datasetRef':a['datasetRef'],'title':a.get('title'),'dataAsOf':a.get('provenance',{}).get('dataAsOf')} for a in artifacts[:8]],ensure_ascii=False)})
    if retrieval is None:
        current = database.session.get(Message, exclude_message_id) if exclude_message_id else None
        messages.append({"role": "user", "content": message_content(current) if current else question})
        return messages
    evidence = "\n\n".join(
        f"[{index}] 文档：{item['document']['title']}；页码：{item['page'].get('start')}\n{item['passage']}"
        for index, item in enumerate(retrieval.get("results", []), 1)
    )
    messages.append({"role": "user", "content": f"问题：{question}\n\n检索到的来源片段：\n{evidence}"})
    return messages
