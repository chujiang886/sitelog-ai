"""主体解析（Phase 3.8.28 T1）—— 从"凭据可信"到"这个人现在还能负责"。

## 为什么不能只信 token 里的角色

Phase 2.2 的登录流程把角色与权限**烘焙进 JWT**（``resolve_principals`` 的结果
写进 payload），运行时由 ``require_permission`` 直接读 payload。对上传、分析这类
业务动作，这个取舍是合理的：省一次查库，且授权变更的延迟窗口（token TTL 60 分钟）
可以接受。

治理动作不适用同一取舍。一个人被撤销治理审批资格，通常正是因为**不再应该由他
负责**（转岗、离职、涉事回避）。如果他手上那张一小时有效期的 token 还能继续
确认治理工作流，那么"撤销"这个动作在最要紧的一小时里是无效的。

所以 ``DbBackedPrincipalResolver`` **每次请求都回权威源重读角色**，token 只用来
证明"你是谁"，不用来证明"你现在能做什么"。这是本阶段有意接受的一次额外查库。

## actor_kind 从哪来

不从请求头来，也不从 token 声明来，而是从**权威源里存在一条 active 的 users 记录**
这一事实推导出来：能在 users 表里查到、未软删、状态 active ⇒ 这是一个真人账号。
凭据若自称 ``actor_kind=agent``（或任何非 user 值），视为它在主动声明自己不是人，
直接拒绝，不做"忽略该声明按真人处理"的宽容。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.errors import (
    IdentityNotHumanError,
    IdentitySubjectInactiveError,
    IdentityTokenInvalidError,
)
from app.identity.permissions import (
    assert_no_forbidden_permission,
    permissions_for_roles,
)
from app.identity.principal import ActorKind, GovernancePrincipal, build_principal
from app.identity.verifier import VerifiedClaims


class PrincipalResolver(ABC):
    """把 ``VerifiedClaims`` 解析成 ``GovernancePrincipal`` 的端口。"""

    @abstractmethod
    async def resolve(self, claims: VerifiedClaims) -> GovernancePrincipal:
        """解析主体；任何不可继续的情形抛 ``IdentityError`` 子类。"""


def _reject_non_human_claim(claims: VerifiedClaims) -> None:
    """凭据自称非真人时直接拒绝（红线⑥）。"""

    declared = str(claims.actor_kind_claim or "").strip().lower()
    if not declared:
        # 未声明：交由权威源判定（Phase 2.2 的 token 就不带这个声明）。
        return
    kind = ActorKind.parse(declared)
    if kind is not ActorKind.USER:
        raise IdentityNotHumanError(
            f"凭据声明 actor_kind={declared!r}，非真实自然人不得进入治理链路（红线⑥）。"
        )


def _resolve_permissions(roles: Sequence[str]):
    """角色 → 治理权限，并对角色名本身做一次禁语扫描。

    扫角色名而不只是扫权限名，是因为权限由角色映射产生：如果有人往数据库里
    塞了一个叫 ``auto-approver`` 的角色，即便它当前映射到空权限集（未知角色
    不贡献权限），这条记录本身也说明授权侧的理解出了问题，应当立即暴露。
    """

    assert_no_forbidden_permission(roles)
    return permissions_for_roles(roles)


class DbBackedPrincipalResolver(PrincipalResolver):
    """权威解析器：以数据库为准（生产路径）。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(self, claims: VerifiedClaims) -> GovernancePrincipal:
        from app.db.models.rbac import Role, UserRole
        from app.db.models.user import User

        _reject_non_human_claim(claims)

        try:
            user_id = uuid.UUID(claims.subject)
        except (TypeError, ValueError) as exc:
            raise IdentityTokenInvalidError(
                f"凭据 sub={claims.subject!r} 不是合法用户标识。"
            ) from exc

        user = await self._db.get(User, user_id)
        if user is None:
            raise IdentitySubjectInactiveError(
                "凭据对应的用户不存在（可能已被彻底删除）。"
            )
        if user.deleted_at is not None or user.status != "active":
            raise IdentitySubjectInactiveError(
                f"用户 {claims.subject} 当前状态为 "
                f"{user.status!r}，不具备治理责任能力。"
            )

        # 组织边界以数据库为准：token 声明的 org 与库中不一致时，
        # 说明凭据被跨租户复用，拒绝。
        db_org = str(user.tenant_id)
        if claims.org_id and claims.org_id != db_org:
            raise IdentityTokenInvalidError(
                "凭据声明的组织与用户实际归属不一致，拒绝跨组织复用凭据。"
            )

        # 关键：角色回权威源重读，不采信 token 里烘焙的旧角色。
        role_rows = await self._db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user.id,
                UserRole.tenant_id == user.tenant_id,
            )
        )
        roles = tuple(sorted(set(role_rows.all())))
        permissions = _resolve_permissions(roles)

        return build_principal(
            actor_id=str(user.id),
            org_id=db_org,
            roles=roles,
            permissions=permissions,
            actor_kind=ActorKind.USER,
            email=user.email,
            display_name=claims.display_name or user.email,
            authenticated_via=claims.scheme,
            issued_at=claims.issued_at,
            expires_at=claims.expires_at,
        )


class ClaimsOnlyPrincipalResolver(PrincipalResolver):
    """无状态解析器：只用凭据声明，不查库。

    适用场景严格限定为两类：
    1. 后端与用户目录不同库的无状态部署（此时权威源是 IdP，不是本地 DB）；
    2. 不涉及用户目录的单元测试。

    代价必须写清楚：**角色撤销要等到 token 过期才生效**。因此它不是生产
    治理路径的默认选择，装配时需要显式指定。
    """

    def __init__(self, *, trust_reason: str) -> None:
        if not str(trust_reason).strip():
            raise ValueError(
                "ClaimsOnlyPrincipalResolver 必须说明为什么可以不查权威源，"
                "以便审计时能还原这一取舍。"
            )
        self._trust_reason = trust_reason

    @property
    def trust_reason(self) -> str:
        return self._trust_reason

    async def resolve(self, claims: VerifiedClaims) -> GovernancePrincipal:
        _reject_non_human_claim(claims)
        if not claims.subject:
            raise IdentityTokenInvalidError("凭据缺少 sub 声明。")

        roles = tuple(claims.roles)
        permissions = _resolve_permissions(roles)
        return build_principal(
            actor_id=claims.subject,
            org_id=claims.org_id,
            roles=roles,
            permissions=permissions,
            actor_kind=ActorKind.USER,
            email=claims.email,
            display_name=claims.display_name or claims.email,
            authenticated_via=claims.scheme,
            issued_at=claims.issued_at,
            expires_at=claims.expires_at,
        )


__all__ = [
    "ClaimsOnlyPrincipalResolver",
    "DbBackedPrincipalResolver",
    "PrincipalResolver",
]
