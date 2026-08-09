"""治理 RBAC 目录种子（Phase 3.8.28 T2）。

与 ``app.core.security.seed_rbac_catalog``（业务角色）并列的治理侧种子。
两者刻意**分开**：业务侧 seed 变更不应顺手给谁发治理权限，治理侧 seed
也不该在业务初始化里被"捎带"执行。

用途分三种：

- Alembic 已升级过的库：迁移里已经种过，这里再跑一次是幂等 no-op；
- 测试/开发用 ``Base.metadata.create_all`` 建的库（不走 alembic）：靠这里补齐；
- 未来新增治理权限点：改 ``app.identity.permissions`` 目录 + 新增迁移，
  这里自动跟随（本模块从目录派生，不重复抄一遍词表）。

授予永远是显式的：``seed_governance_rbac`` 只建"角色和权限的目录"，
**不给任何人授权**。谁拥有治理角色必须由 ``assign_governance_role`` 逐个
写入 ``user_roles``，且需要指定 tenant —— 治理权限不存在"全局默认拥有"。
"""

from __future__ import annotations

import uuid

from app.db.models.rbac import Permission, Role, RolePermission, UserRole
from app.db.models.user import User
from app.identity.permissions import (
    ALL_GOVERNANCE_PERMISSIONS,
    GOVERNANCE_ROLE_PERMISSIONS,
    GOVERNANCE_ROLES,
    GovernancePermission,
    is_governance_role,
)

#: 角色描述，与迁移 ``4c9d7e1f2a30`` 保持一致。
GOVERNANCE_ROLE_DESCRIPTIONS: dict[str, str] = {
    "governance-admin": "治理管理员：全部治理读写权限",
    "governance-reviewer": "治理研判人：可研判与处置，不可查看全量审计",
    "governance-auditor": "治理审计员：全量只读，无任何写权限（职责分离）",
    "governance-viewer": "治理观察者：只读工作流/研判列表/概览",
}

GOVERNANCE_PERMISSION_DESCRIPTIONS: dict[GovernancePermission, str] = {
    GovernancePermission.WORKFLOW_READ: "查看治理工作流任务与状态",
    GovernancePermission.REVIEW_READ: "查看待人工研判的治理事项",
    GovernancePermission.REVIEW_CONFIRM: "提交一次人工研判（判断仍由自然人做出）",
    GovernancePermission.EXECUTION_READ: "查看治理动作的执行记录",
    GovernancePermission.AUDIT_READ: "查看治理审计留痕全量",
    GovernancePermission.SUMMARY_READ: "查看治理概览汇总",
    GovernancePermission.WORKFLOW_REPORT: "登记一条治理工作流（人工上报）",
    GovernancePermission.EXECUTION_SUBMIT: "提交治理处置结果（人工执行）",
    GovernancePermission.WORKFLOW_CLOSE: "宣布治理工作流闭环（人工负责）",
}


def seed_governance_rbac(db) -> None:
    """幂等写入治理 roles / permissions / role_permissions（不提交）。

    只建目录，不授权给任何用户。
    """

    perm_objs: dict[str, Permission] = {}
    for perm in ALL_GOVERNANCE_PERMISSIONS:
        name = perm.value
        existing = db.query(Permission).filter_by(name=name).one_or_none()
        if existing is None:
            existing = Permission(
                name=name,
                description=GOVERNANCE_PERMISSION_DESCRIPTIONS.get(perm, ""),
            )
            db.add(existing)
            db.flush()
        perm_objs[name] = existing

    role_objs: dict[str, Role] = {}
    for role_name in GOVERNANCE_ROLES:
        existing = db.query(Role).filter_by(name=role_name).one_or_none()
        if existing is None:
            existing = Role(
                name=role_name,
                description=GOVERNANCE_ROLE_DESCRIPTIONS.get(role_name, ""),
            )
            db.add(existing)
            db.flush()
        role_objs[role_name] = existing

    for role_name, granted in GOVERNANCE_ROLE_PERMISSIONS.items():
        role = role_objs[role_name]
        for perm in granted:
            perm_row = perm_objs[perm.value]
            link = (
                db.query(RolePermission)
                .filter_by(role_id=role.id, permission_id=perm_row.id)
                .one_or_none()
            )
            if link is None:
                db.add(RolePermission(role_id=role.id, permission_id=perm_row.id))


def assign_governance_role(
    db, user: User, role_name: str, tenant_id: uuid.UUID
) -> None:
    """把治理角色显式授予某用户（不提交）。

    非治理角色名一律拒绝：本函数是治理授权的唯一入口，如果它同时能授业务
    角色，"谁在什么时候获得了治理权限"这条线就会混进业务初始化流程里，
    以后再想审计"治理权限是怎么来的"就没法只看一处。
    """

    if not is_governance_role(role_name):
        raise ValueError(
            f"{role_name!r} 不是治理角色；业务角色请用 "
            "app.core.security.assign_user_role"
        )
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        raise ValueError(
            f"治理角色 {role_name!r} 尚未入库，请先执行 seed_governance_rbac / alembic 升级"
        )
    existing = (
        db.query(UserRole)
        .filter_by(user_id=user.id, role_id=role.id, tenant_id=tenant_id)
        .one_or_none()
    )
    if existing is None:
        db.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=tenant_id))


__all__ = [
    "GOVERNANCE_PERMISSION_DESCRIPTIONS",
    "GOVERNANCE_ROLE_DESCRIPTIONS",
    "assign_governance_role",
    "seed_governance_rbac",
]
