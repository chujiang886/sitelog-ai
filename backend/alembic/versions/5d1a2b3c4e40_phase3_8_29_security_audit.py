"""phase3.8.29 security audit action expansion

Revision ID: 5d1a2b3c4e40
Revises: 4c9d7e1f2a30
Create Date: 2026-08-10 10:00:00.000000

Phase 3.8.29 T4：扩展 ``audit_logs.action`` 的 CheckConstraint，允许新增的
安全审计动作：``token_refresh`` / ``permission_denied`` / ``identity_failure``。
这些事件由 ``app.core.security_audit`` 以 append-only 方式写入，用于事后还原
"谁在何时登入/登出/续期/被拒/身份失败"。

### 为什么用时间点快照

与 4c9d7e1f2a30 同原则：约束文本在此固化，未来若再增动作请新增迁移，
不要就地改这张表的常量，保证历史库可复现。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d1a2b3c4e40"
down_revision: str | Sequence[str] | None = "4c9d7e1f2a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_CHECK = (
    "action in ('create', 'update', 'delete', 'login', 'logout', "
    "'export', 'import', 'token_refresh', 'permission_denied', "
    "'identity_failure')"
)


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("audit_action_valid", type_="check")
        batch_op.create_check_constraint("audit_action_valid", _NEW_CHECK)


def downgrade() -> None:
    _OLD_CHECK = (
        "action in ('create', 'update', 'delete', 'login', 'logout', "
        "'export', 'import')"
    )
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("audit_action_valid", type_="check")
        batch_op.create_check_constraint("audit_action_valid", _OLD_CHECK)
