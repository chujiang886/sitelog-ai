"""AuditLog 模型：追加写审计记录。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


class AuditLog(Base):
    """审计日志表：仅追加，不允许更新/删除业务字段。"""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "action in ('create', 'update', 'delete', 'login', 'logout', 'export', 'import')",
            name="audit_action_valid",
        ),
        Index("ix_audit_logs_target", "tenant_id", "target_type", "target_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"target_type={self.target_type!r}>"
        )
