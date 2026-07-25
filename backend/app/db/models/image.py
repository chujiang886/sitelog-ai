"""Image 模型：用户上传图片 + Vision Agent 结构化分析结果。

Phase 1 / T08：
- 图片本地落盘到 ``backend/storage/uploads/{tenant_id}/{sha256}.{ext}``
  （占位实现，Phase 2 切到 MinIO，参见 technical_debt.md TD-015）；
- ``vision_status`` 状态机：Pending → Processing → Done / Failed；
- ``vision_result`` 存 JSONB，由 Vision Agent 异步写入。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, JSON

from app.db.base import Base
from app.db.models.tenant import GUID


# --------------------------------------------------------------------------- #
# 状态机常量                                                                   #
# --------------------------------------------------------------------------- #

VISION_STATUS_PENDING: str = "Pending"
VISION_STATUS_PROCESSING: str = "Processing"
VISION_STATUS_DONE: str = "Done"
VISION_STATUS_FAILED: str = "Failed"

VISION_STATUS_VALUES: tuple[str, ...] = (
    VISION_STATUS_PENDING,
    VISION_STATUS_PROCESSING,
    VISION_STATUS_DONE,
    VISION_STATUS_FAILED,
)


class Image(Base):
    """图片表：存储上传文件元数据 + Vision Agent 分析结果。"""

    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    vision_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VISION_STATUS_PENDING
    )
    vision_result: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "vision_status in ('Pending', 'Processing', 'Done', 'Failed')",
            name="image_vision_status_valid",
        ),
        Index("ix_images_tenant_project", "tenant_id", "project_id"),
        Index("ix_images_tenant_sha256", "tenant_id", "sha256"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Image id={self.id} vision_status={self.vision_status!r}>"


__all__ = [
    "Image",
    "VISION_STATUS_PENDING",
    "VISION_STATUS_PROCESSING",
    "VISION_STATUS_DONE",
    "VISION_STATUS_FAILED",
    "VISION_STATUS_VALUES",
]