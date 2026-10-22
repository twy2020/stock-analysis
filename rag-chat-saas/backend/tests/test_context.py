from __future__ import annotations

from datetime import timedelta

from app.context import build_messages, compact_conversation
from app.extensions import database
from app.models import Conversation, Message, User, now


def add_history(conversation: Conversation, user: User, count: int) -> list[Message]:
    rows = []
    started_at = now()
    for index in range(count):
        row = Message(
            conversation_id=conversation.id,
            organization_id=user.organization_id,
            owner_id=user.id,
            role="USER" if index % 2 == 0 else "ASSISTANT",
            content=f"历史消息 {index + 1}",
            status="COMPLETED",
            created_at=started_at + timedelta(microseconds=index),
        )
        database.session.add(row)
        rows.append(row)
    database.session.commit()
    return rows


def test_compaction_summarizes_old_messages_once_and_keeps_recent_turns(app):
    with app.app_context():
        user = database.session.query(User).filter_by(username="admin").one()
        conversation = Conversation(
            organization_id=user.organization_id,
            owner_id=user.id,
            title="长对话",
            knowledge_base_id="kb-1",
        )
        database.session.add(conversation)
        database.session.commit()
        history = add_history(conversation, user, 14)

        changed = compact_conversation(conversation, keep_recent=8, compact_after=12)
        database.session.commit()

        assert changed is True
        assert conversation.summary_through_message_id == history[5].id
        assert "用户：历史消息 1" in conversation.rolling_summary
        assert "助手：历史消息 6" in conversation.rolling_summary

        summary = conversation.rolling_summary
        assert compact_conversation(conversation, keep_recent=8, compact_after=12) is False
        assert conversation.rolling_summary == summary

        prompt = build_messages(conversation, "新问题", {"results": []})
        rendered = "\n".join(item["content"] for item in prompt)
        assert rendered.splitlines().count("历史摘要：用户：历史消息 1") == 1
        assert "历史消息 6" in rendered
        assert "历史消息 7" in rendered
        assert "历史消息 14" in rendered


def test_compaction_appends_only_newly_eligible_messages(app):
    with app.app_context():
        user = database.session.query(User).filter_by(username="admin").one()
        conversation = Conversation(
            organization_id=user.organization_id,
            owner_id=user.id,
            title="继续对话",
            knowledge_base_id="kb-1",
        )
        database.session.add(conversation)
        database.session.commit()
        first = add_history(conversation, user, 14)
        compact_conversation(conversation, keep_recent=8, compact_after=12)
        database.session.commit()

        add_history(conversation, user, 4)
        assert compact_conversation(conversation, keep_recent=8, compact_after=12) is True
        assert conversation.summary_through_message_id == first[9].id
        summary_lines = conversation.rolling_summary.splitlines()
        assert summary_lines.count("用户：历史消息 1") == 1
        assert summary_lines.count("助手：历史消息 10") == 1
