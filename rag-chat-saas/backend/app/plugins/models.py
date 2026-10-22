from sqlalchemy import String, Text, Integer, Float, JSON, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base, now
from datetime import datetime
import uuid


def identifier():
    return str(uuid.uuid4())


class KnowledgeSpace(Base):
    __tablename__ = 'plugin_knowledge_spaces'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    service_id: Mapped[str] = mapped_column(String(120), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    context: Mapped[dict] = mapped_column(JSON)
    kind: Mapped[str] = mapped_column(String(20), default='temporary')
    name: Mapped[str] = mapped_column(String(200), default='')
    promotion_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class KnowledgeDocument(Base):
    __tablename__ = 'plugin_knowledge_documents'
    space_id: Mapped[str] = mapped_column(ForeignKey('plugin_knowledge_spaces.id', ondelete='CASCADE'), primary_key=True)
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    revision: Mapped[str] = mapped_column(String(160))
    chunks: Mapped[list] = mapped_column(JSON)


class AnalysisRun(Base):
    __tablename__ = 'plugin_analysis_runs'
    __table_args__ = (UniqueConstraint('service_id', 'tenant_id', 'request_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    request_id: Mapped[str] = mapped_column(String(36))
    service_id: Mapped[str] = mapped_column(String(120), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120))
    context: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    space_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='QUEUED', index=True)
    content: Mapped[str] = mapped_column(Text, default='')
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)
    completed_at: Mapped[datetime | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(index=True)


class AnalysisEvent(Base):
    __tablename__ = 'plugin_analysis_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('plugin_analysis_runs.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)


class ChatImage(Base):
    __tablename__ = 'chat_images'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(80))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
