"""phase3.8.28 governance rbac

Revision ID: 4c9d7e1f2a30
Revises: 3826a1b2c3d4
Create Date: 2026-08-09 16:20:00.000000

Phase 3.8.28 T2：把治理权限从"前端硬编码"迁移到"数据库里的真实 RBAC 目录"。

做两件事：

1. 放宽 ``roles`` 的 ``role_name_valid`` CHECK 约束，允许 4 个治理角色入库。
   Phase 2.2 把角色名锁死在 admin/designer/viewer，治理角色在迁移前**根本插不进去**，
   这也是此前治理接口只能靠 HTTP header 认身份的直接原因之一。

2. 幂等种入 6 个治理权限点、4 个治理角色，以及两者的关联。

### 为什么这里写字面量而不是 import 应用层目录

迁移是**时间点快照**：它描述"这次升级把库改成什么样"，而不是"库应当永远等于
当前代码里的常量"。如果这里 ``from app.identity.permissions import ...``，将来有人
改了目录常量，这个已经跑过的迁移会在新库上产生与旧库不同的结果，历史不可复现。

一致性由测试保证：``backend/tests/test_governance_rbac.py`` 断言"迁移后的库内容
== 当前应用目录"。目录一变，测试立刻红，逼出一个新的迁移 —— 这正是我们要的。
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import NAMING_CONVENTION
from app.db.models.tenant import GUID

# revision identifiers, used by Alembic.
revision: str = "4c9d7e1f2a30"
down_revision: str | Sequence[str] | None = "3826a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --------------------------------------------------------------------------- #
# 时间点快照常量（勿改；要改请新增迁移）                                          #
# --------------------------------------------------------------------------- #

OLD_ROLE_NAMES: tuple[str, ...] = ("admin", "designer", "viewer")
GOVERNANCE_ROLE_NAMES: tuple[str, ...] = (
    "governance-admin",
    "governance-reviewer",
    "governance-auditor",
    "governance-viewer",
)
NEW_ROLE_NAMES: tuple[str, ...] = OLD_ROLE_NAMES + GOVERNANCE_ROLE_NAMES

GOVERNANCE_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("governance:workflow:read", "查看治理工作流任务与状态"),
    ("governance:review:read", "查看待人工研判的治理事项"),
    ("governance:review:confirm", "提交一次人工研判（判断仍由自然人做出）"),
    ("governance:execution:read", "查看治理动作的执行记录"),
    ("governance:audit:read", "查看治理审计留痕全量"),
    ("governance:summary:read", "查看治理概览汇总"),
    ("governance:workflow:report", "登记一条治理工作流（人工上报）"),
    ("governance:execution:submit", "提交治理处置结果（人工执行）"),
    ("governance:workflow:close", "宣布治理工作流闭环（人工负责）"),
)

GOVERNANCE_ROLE_DESCRIPTIONS: dict[str, str] = {
    "governance-admin": "治理管理员：全部治理读写权限",
    "governance-reviewer": "治理研判人：可研判与处置，不可查看全量审计",
    "governance-auditor": "治理审计员：全量只读，无任何写权限（职责分离）",
    "governance-viewer": "治理观察者：只读工作流/研判列表/概览",
}

GOVERNANCE_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "governance-admin": (
        "governance:workflow:read",
        "governance:review:read",
        "governance:review:confirm",
        "governance:execution:read",
        "governance:audit:read",
        "governance:summary:read",
        "governance:workflow:report",
        "governance:execution:submit",
        "governance:workflow:close",
    ),
    "governance-reviewer": (
        "governance:workflow:read",
        "governance:review:read",
        "governance:review:confirm",
        "governance:execution:read",
        "governance:summary:read",
        "governance:workflow:report",
        "governance:execution:submit",
        "governance:workflow:close",
    ),
    "governance-auditor": (
        "governance:workflow:read",
        "governance:review:read",
        "governance:execution:read",
        "governance:audit:read",
        "governance:summary:read",
    ),
    "governance-viewer": (
        "governance:workflow:read",
        "governance:review:read",
        "governance:summary:read",
    ),
}


def _check_clause(names: Sequence[str]) -> str:
    return "name in (" + ", ".join(f"'{n}'" for n in names) + ")"


def _roles_table(check_names: Sequence[str]) -> sa.Table:
    """``roles`` 的完整快照定义，供 batch_alter_table 在 SQLite 上重建表使用。

    SQLite 无法 ALTER 掉一个 CHECK 约束，batch 模式必须"照着定义重建表"；
    反射又拿不全 SQLite 的 CHECK，所以这里显式给出 ``copy_from``。
    """

    meta = sa.MetaData(naming_convention=NAMING_CONVENTION)
    return sa.Table(
        "roles",
        meta,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(_check_clause(check_names), name="role_name_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )


# 轻量表句柄，仅用于 DML。
_perm_dml = sa.table(
    "permissions",
    sa.column("id", GUID()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
)
_role_dml = sa.table(
    "roles",
    sa.column("id", GUID()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
)
_link_dml = sa.table(
    "role_permissions",
    sa.column("role_id", GUID()),
    sa.column("permission_id", GUID()),
)
_user_role_dml = sa.table(
    "user_roles",
    sa.column("role_id", GUID()),
)


def _existing_ids(conn, table: sa.TableClause, names: Sequence[str]) -> dict[str, uuid.UUID]:
    rows = conn.execute(
        sa.select(table.c.id, table.c.name).where(table.c.name.in_(list(names)))
    ).fetchall()
    return {row.name: row.id for row in rows}


def upgrade() -> None:
    # 1) 放宽角色白名单（旧 → 新）
    with op.batch_alter_table(
        "roles", schema=None, copy_from=_roles_table(OLD_ROLE_NAMES)
    ) as batch_op:
        # 传裸名：batch 会按 NAMING_CONVENTION 补出 ck_roles_ 前缀。
        batch_op.drop_constraint("role_name_valid", type_="check")
        batch_op.create_check_constraint("role_name_valid", _check_clause(NEW_ROLE_NAMES))

    conn = op.get_bind()

    # 2) 幂等种入治理权限点
    perm_names = [name for name, _ in GOVERNANCE_PERMISSIONS]
    perm_ids = _existing_ids(conn, _perm_dml, perm_names)
    missing_perms = [
        {"id": uuid.uuid4(), "name": name, "description": desc}
        for name, desc in GOVERNANCE_PERMISSIONS
        if name not in perm_ids
    ]
    if missing_perms:
        conn.execute(_perm_dml.insert(), missing_perms)
        perm_ids.update({row["name"]: row["id"] for row in missing_perms})

    # 3) 幂等种入治理角色
    role_ids = _existing_ids(conn, _role_dml, GOVERNANCE_ROLE_NAMES)
    missing_roles = [
        {
            "id": uuid.uuid4(),
            "name": name,
            "description": GOVERNANCE_ROLE_DESCRIPTIONS[name],
        }
        for name in GOVERNANCE_ROLE_NAMES
        if name not in role_ids
    ]
    if missing_roles:
        conn.execute(_role_dml.insert(), missing_roles)
        role_ids.update({row["name"]: row["id"] for row in missing_roles})

    # 4) 幂等种入角色→权限关联
    existing_links = {
        (row.role_id, row.permission_id)
        for row in conn.execute(
            sa.select(_link_dml.c.role_id, _link_dml.c.permission_id).where(
                _link_dml.c.role_id.in_(list(role_ids.values()))
            )
        ).fetchall()
    }
    new_links = []
    for role_name, granted in GOVERNANCE_ROLE_PERMISSIONS.items():
        rid = role_ids[role_name]
        for perm_name in granted:
            pid = perm_ids[perm_name]
            if (rid, pid) not in existing_links:
                new_links.append({"role_id": rid, "permission_id": pid})
    if new_links:
        conn.execute(_link_dml.insert(), new_links)


def downgrade() -> None:
    conn = op.get_bind()

    role_ids = _existing_ids(conn, _role_dml, GOVERNANCE_ROLE_NAMES)
    perm_ids = _existing_ids(
        conn, _perm_dml, [name for name, _ in GOVERNANCE_PERMISSIONS]
    )

    # 先摘关联，再摘用户授予，最后摘角色/权限本身：
    # SQLite 默认不开 FK 强制，不能指望 ON DELETE CASCADE 帮忙清理。
    if role_ids:
        rid_list = list(role_ids.values())
        conn.execute(_link_dml.delete().where(_link_dml.c.role_id.in_(rid_list)))
        conn.execute(
            _user_role_dml.delete().where(_user_role_dml.c.role_id.in_(rid_list))
        )
        conn.execute(_role_dml.delete().where(_role_dml.c.id.in_(rid_list)))
    if perm_ids:
        pid_list = list(perm_ids.values())
        conn.execute(_link_dml.delete().where(_link_dml.c.permission_id.in_(pid_list)))
        conn.execute(_perm_dml.delete().where(_perm_dml.c.id.in_(pid_list)))

    with op.batch_alter_table(
        "roles", schema=None, copy_from=_roles_table(NEW_ROLE_NAMES)
    ) as batch_op:
        # 传裸名：batch 会按 NAMING_CONVENTION 补出 ck_roles_ 前缀。
        batch_op.drop_constraint("role_name_valid", type_="check")
        batch_op.create_check_constraint("role_name_valid", _check_clause(OLD_ROLE_NAMES))
