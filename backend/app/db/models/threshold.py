"""ThresholdConfig 模型：强制复核阈值占位。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


class ThresholdConfig(Base):
    """阈值配置表：强制复核等业务阈值（pending_verification）。"""

    __tablename__ = "threshold_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v0.1.0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "key", "version", name="uq_threshold_configs_scope"
        ),
        CheckConstraint(
            "status in ('draft', 'verified', 'deprecated')",
            name="threshold_status_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<ThresholdConfig id={self.id} key={self.key!r} version={self.version!r}>"
