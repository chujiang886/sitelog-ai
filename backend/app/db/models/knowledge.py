"""Knowledge 模型：知识规则与案例。Phase 0 占位 + pending_verification。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


class KnowledgeRule(Base):
    """知识规则表：category/key/value 三元组，pending_verification。"""

    __tablename__ = "knowledge_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="pending_verification")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v0.1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "category", "key", "version", name="uq_knowledge_rules_scope"
        ),
        CheckConstraint(
            "status in ('draft', 'verified', 'deprecated')",
            name="knowledge_rule_status_valid",
        ),
        Index("ix_knowledge_rules_category", "tenant_id", "category"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<KnowledgeRule id={self.id} category={self.category!r} key={self.key!r}>"


class KnowledgeCase(Base):
    """知识案例表：scenario/outcome JSON。"""

    __tablename__ = "knowledge_cases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v0.1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'verified', 'deprecated')",
            name="knowledge_case_status_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<KnowledgeCase id={self.id} title={self.title!r}>"
