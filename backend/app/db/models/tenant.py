"""Tenant 模型：组织/租户，所有业务表的外键起点。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator

from app.db.base import Base


class GUID(TypeDecorator):
    """跨 PostgreSQL / SQLite 的 UUID 类型。

    PostgreSQL 使用原生 UUID；其他方言回落到 CHAR(36) 存储。
    Phase 0 主要在 SQLite 上做迁移演练，因此兼容两种实现。
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class Tenant(Base):
    """租户表（Phase 3 多租户隔离的起点）。

    字段保持最小集合：id/name/slug/status/created_at/deleted_at。
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
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
        CheckConstraint(
            "status in ('active', 'suspended', 'archived')",
            name="tenant_status_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Tenant id={self.id} slug={self.slug!r}>"
