"""Conversation 模型：用户与 Core Agent 的一次多轮对话。

字段集（Phase 1 / T06b）：
- ``id``        UUID PK
- ``tenant_id`` FK → tenants.id，租户隔离
- ``user_id``   FK → users.id，会话拥有者
- ``project_id`` FK → projects.id（可选），会话可挂到具体项目
- ``title``     会话标题（默认 "未命名会话"）
- ``status``    'Active' / 'Closed' / 'Archived'
- ``state``     额外状态字段，CHECK 约束 'Active'（保留向后兼容）
- ``created_at`` / ``updated_at`` / ``deleted_at``
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.db.models.tenant import GUID


class Conversation(Base):
    """会话表：聚合一次多轮对话的所有 message。"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="未命名会话")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="Active")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="Active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('Active', 'Closed', 'Archived')",
            name="conversation_status_valid",
        ),
        CheckConstraint(
            "state in ('Active', 'Closed', 'Archived')",
            name="conversation_state_valid",
        ),
        Index("ix_conversations_tenant_user", "tenant_id", "user_id"),
        Index("ix_conversations_tenant_updated", "tenant_id", "updated_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Conversation id={self.id} status={self.status!r} title={self.title!r}>"