"""Agent 注册表：保存 Agent 名称/版本/manifest 元数据。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


class Agent(Base):
    """Agent 注册表：记录每个 Agent 的 manifest（占位空 dict）。"""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v0.1.0")
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_agents_tenant_name"),
        CheckConstraint(
            "status in ('active', 'disabled', 'experimental')",
            name="agent_status_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Agent id={self.id} name={self.name!r} version={self.version!r}>"
