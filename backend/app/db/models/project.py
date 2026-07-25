"""Project 模型：建筑开口项目聚合根。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


class Project(Base):
    """项目表：聚合 input/output/evidence 三个 JSONB 大字段。"""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    address: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    floor: Mapped[int | None] = mapped_column(nullable=True)
    orientation: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="Draft")

    # Phase 0 在 SQLite 上演练，使用 JSON 类型；PG 上等价于 JSONB。
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

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
            "state in ('Draft', 'Submitted', 'Analyzing', 'Designed', 'Quoted', 'Closed')",
            name="project_state_valid",
        ),
        CheckConstraint(
            "status in ('pending', 'analysis', 'design', 'quotation', 'construction', 'completed')",
            name="project_status_valid",
        ),
        Index("ix_projects_tenant_state", "tenant_id", "state"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Project id={self.id} state={self.state!r}>"
