"""RBAC 权限模型（Phase 2.2 / 2.2.6）。

四张表组成最小 RBAC：
- ``roles``：全局角色目录（admin / designer / viewer）；
- ``permissions``：权限点（resource:action）；
- ``role_permissions``：角色→权限关联；
- ``user_roles``：用户→角色关联（按 tenant 维度，支持每租户多角色）。

设计要点：
- ``User.role`` legacy 列保留不动，RBAC 以 ``user_roles`` 为准；
- 所有外键级联到各自父表，软删父表时关联随删；
- GUID 复用 ``tenant.py`` 的跨方言 UUID 类型。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.db.models.tenant import GUID


class Role(Base):
    """全局角色目录。本阶段固定三种：admin / designer / viewer。"""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "name in ('admin', 'designer', 'viewer')",
            name="role_name_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Role id={self.id} name={self.name!r}>"


class Permission(Base):
    """权限点，形如 ``resource:action``。"""

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<Permission id={self.id} name={self.name!r}>"


class RolePermission(Base):
    """角色→权限关联（多对多连接表）。"""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<RolePermission role_id={self.role_id} perm_id={self.permission_id}>"


class UserRole(Base):
    """用户→角色关联（按 tenant 维度，支持每租户多角色）。"""

    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "tenant_id", name="uq_user_role_tenant"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<UserRole user_id={self.user_id} role_id={self.role_id} tenant_id={self.tenant_id}>"
