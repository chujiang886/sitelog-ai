"""Message 模型：会话内单条消息（user / assistant / system）。

字段集（Phase 1 / T06b）：
- ``id``             UUID PK
- ``tenant_id``      FK → tenants.id，租户隔离
- ``conversation_id`` FK → conversations.id
- ``role``           'user' / 'assistant' / 'system'
- ``content``        TEXT 主体内容
- ``intent``         JSONB，NLU 提取结果（含 confidence/method/matched_keywords）
- ``evidence``       JSONB，证据链（agent_steps / llm_routes 等）
- ``created_at``     UTC 时间戳
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime

from app.db.base import Base
from app.db.models.tenant import GUID


class Message(Base):
    """消息表：会话内单条消息记录。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "role in ('user', 'assistant', 'system')",
            name="message_role_valid",
        ),
        Index("ix_messages_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<Message id={self.id} role={self.role!r} "
            f"conversation_id={self.conversation_id}>"
        )