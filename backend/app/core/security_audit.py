"""安全审计落库（Phase 3.8.29 T4）—— 不可修改、append-only。

## 记录的事件

- ``login``            登录成功
- ``logout``           登出（凭据失效）
- ``token_refresh``   令牌刷新成功
- ``permission_denied`` 治理权限被拒绝（403）
- ``identity_failure`` 身份校验失败（401/403 身份类异常）

## 为什么是 append-only

审计的本质是「事后还原」。本模块**只提供写入**，且写入对象 ``AuditLog`` 在建表
时即被约束为「仅追加」：

- 没有任何 UPDATE/DELETE 路径（本模块不提供，路由层也不提供）；
- ``AuditLog`` 的 ``action`` 受 ``CheckConstraint`` 约束，只允许上列取值，
  把"有人试图写一条不属于审计范畴的记录"挡在数据库层。

试图修改/删除审计即等于篡改证据，因此从结构上不可行，而非靠"大家别乱改"的约定。

## 未知主体的处理

身份失败发生时往往还不知道「是谁」（坏 token、跨组织复用）。``AuditLog.tenant_id``
非空约束不能破，故用全零系统租户 ``SECURITY_AUDIT_SYSTEM_TENANT`` 标记
"该事件不属于任何真实租户"，查询时一眼可辨。
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog

#: 允许写入的安全审计动作（与 AuditLog 的 CheckConstraint 一致）。
SECURITY_AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "login",
        "logout",
        "token_refresh",
        "permission_denied",
        "identity_failure",
    }
)

#: 全零系统租户：用于"尚不知道真实租户"的安全事件（坏 token、跨组织复用等）。
SECURITY_AUDIT_SYSTEM_TENANT = uuid.UUID(int=0)


class SecurityAuditError(ValueError):
    """审计写入被拒绝（动作不在允许集合 / 参数非法）。"""


def _coerce_tenant(tenant_id: Optional[uuid.UUID]) -> uuid.UUID:
    if tenant_id is None:
        return SECURITY_AUDIT_SYSTEM_TENANT
    return tenant_id


async def record_security_event(
    db: AsyncSession,
    *,
    action: str,
    tenant_id: Optional[uuid.UUID],
    actor_id: Optional[uuid.UUID],
    target_id: str = "",
    detail: str = "",
) -> AuditLog:
    """追加一条安全审计记录（不可修改）。

    不在 ``SECURITY_AUDIT_ACTIONS`` 内的动作一律拒绝 —— 审计范围由这张表锁死，
    新增动作必须先改约束再写代码。
    """

    if action not in SECURITY_AUDIT_ACTIONS:
        raise SecurityAuditError(
            f"拒绝写入未授权的安全审计动作 {action!r}；"
            f"允许集合：{sorted(SECURITY_AUDIT_ACTIONS)}。"
        )
    row = AuditLog(
        tenant_id=_coerce_tenant(tenant_id),
        actor_id=actor_id,
        action=action,
        target_type="security_event",
        target_id=target_id or action,
        payload={
            "detail": detail or "",
            "append_only": True,
        },
    )
    db.add(row)
    # 审计写入独立落库：即使后续业务事务回滚，安全留痕也应保留。
    await db.commit()
    return row


__all__ = [
    "SECURITY_AUDIT_ACTIONS",
    "SECURITY_AUDIT_SYSTEM_TENANT",
    "SecurityAuditError",
    "record_security_event",
]
