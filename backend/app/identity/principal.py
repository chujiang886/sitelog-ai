"""治理主体（Phase 3.8.28 T1）。

``GovernancePrincipal`` 是治理层唯一承认的"谁"。它与 Phase 3.8.26/27 使用的
``DashboardUser`` 的根本差别在于**来源**：

- ``DashboardUser`` 由 HTTP 请求头直接构造 —— 客户端说自己是谁就是谁；
- ``GovernancePrincipal`` **只能**由 ``IdentityAuthenticationService`` 在校验
  完签名、有效期、并向权威数据源确认主体仍然有效之后构造。

为了让"只能这样构造"不只是一句约定，本类在 ``__post_init__`` 里做了三件事：
校验 ``actor_kind`` 必为真人、校验权限集不含禁语、校验必填责任字段非空。
任何一处不满足直接抛错，**不存在"部分可用的主体"**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from app.identity.errors import (
    IdentityNotHumanError,
    IdentityTokenInvalidError,
)
from app.identity.permissions import (
    GovernancePermission,
    assert_no_forbidden_permission,
)


class ActorKind(str, Enum):
    """主体类别。

    刻意保留 ``AGENT`` / ``SERVICE`` / ``UNKNOWN`` 三个取值 —— 系统里确实
    存在这些主体，把它们从类型系统里抹掉只会让判断逻辑无处安放。治理边界
    不是"假装非人类不存在"，而是"承认它们存在并在入口处挡住"。
    """

    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: Any) -> "ActorKind":
        """宽进严出：不认识的取值一律归为 ``UNKNOWN``（后续会被拒绝）。"""

        text = str(value or "").strip().lower()
        for member in cls:
            if member.value == text:
                return member
        return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class GovernancePrincipal:
    """经后端完整校验后的治理责任主体。

    字段全部来自服务端裁定，没有任何一项直接采信客户端输入。
    """

    #: 责任人稳定标识（用户主键字符串，非邮箱、非显示名）。
    actor_id: str
    #: 组织/租户标识。**由主体自身携带**，不接受请求方指定。
    org_id: str
    #: 主体类别。构造后恒为 ``USER``（见 ``__post_init__``）。
    actor_kind: ActorKind = ActorKind.USER
    email: str = ""
    display_name: str = ""
    #: 该主体在本组织下的全部角色（含业务角色，便于审计还原上下文）。
    roles: tuple[str, ...] = ()
    #: 治理权限集（由治理角色解析而来，业务角色贡献空集）。
    permissions: frozenset[GovernancePermission] = field(
        default_factory=frozenset
    )
    #: 认证方式，用于审计还原"这次责任是怎么被确认的"。
    authenticated_via: str = "jwt"
    #: 凭据签发/过期时间（Unix 秒），仅供审计与前端续期提示。
    issued_at: int = 0
    expires_at: int = 0

    def __post_init__(self) -> None:
        if not str(self.actor_id).strip():
            raise IdentityTokenInvalidError(
                "治理主体缺少 actor_id：无法归属责任，拒绝构造。"
            )
        if not str(self.org_id).strip():
            raise IdentityTokenInvalidError(
                "治理主体缺少 org_id：无法判定组织边界，拒绝构造。"
            )
        if self.actor_kind is not ActorKind.USER:
            # 红线⑥：治理责任只能落到自然人身上。
            raise IdentityNotHumanError(
                f"主体 {self.actor_id!r} 的类别为 {self.actor_kind.value!r}，"
                "非真实自然人不得成为治理主体（红线⑥）。"
            )
        assert_no_forbidden_permission(p.value for p in self.permissions)

    # ------------------------------------------------------------------ #
    # 查询                                                                #
    # ------------------------------------------------------------------ #

    def has(self, permission: GovernancePermission) -> bool:
        """是否持有某治理权限（默认拒绝：不在集合里就是没有）。"""

        return permission in self.permissions

    def governance_roles(self) -> tuple[str, ...]:
        """仅返回治理角色，过滤掉业务角色（审计展示用）。"""

        from app.identity.permissions import is_governance_role

        return tuple(r for r in self.roles if is_governance_role(r))

    def is_expired(self, *, now: int | None = None) -> bool:
        """凭据是否已过期（``expires_at == 0`` 视为未声明，不判过期）。"""

        if not self.expires_at:
            return False
        current = now if now is not None else int(
            datetime.now(tz=timezone.utc).timestamp()
        )
        return current > self.expires_at

    # ------------------------------------------------------------------ #
    # 序列化                                                              #
    # ------------------------------------------------------------------ #

    def to_public_dict(self) -> dict[str, Any]:
        """返回给前端的身份视图。

        不含 token、不含密码学材料；``permissions`` 用于**渲染**（决定按钮
        灰不灰），后端仍会对每个请求独立判定，前端结果不具备授权效力。
        """

        return {
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind.value,
            "org_id": self.org_id,
            "email": self.email,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "governance_roles": list(self.governance_roles()),
            "permissions": sorted(p.value for p in self.permissions),
            "authenticated_via": self.authenticated_via,
            "expires_at": self.expires_at,
        }

    def to_audit_context(self, *, action: str, resource: str) -> dict[str, Any]:
        """T4 责任五元组：user_id / role / timestamp / action / resource。

        ``role`` 取治理角色（无治理角色时退回全部角色），保证审计里看到的
        是"以什么身份做的这件事"，而不是这个人碰巧还有哪些业务角色。
        """

        gov_roles = self.governance_roles() or self.roles
        return {
            "user_id": self.actor_id,
            "role": ",".join(gov_roles),
            "roles": list(self.roles),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            "resource": resource,
            "org_id": self.org_id,
            "actor_kind": self.actor_kind.value,
            "authenticated_via": self.authenticated_via,
        }


def build_principal(
    *,
    actor_id: str,
    org_id: str,
    roles: Iterable[str],
    permissions: Iterable[GovernancePermission],
    actor_kind: ActorKind = ActorKind.USER,
    email: str = "",
    display_name: str = "",
    authenticated_via: str = "jwt",
    issued_at: int = 0,
    expires_at: int = 0,
    extra_claims: Mapping[str, Any] | None = None,
) -> GovernancePrincipal:
    """统一构造入口（便于测试与未来适配器复用）。"""

    del extra_claims  # 预留：OIDC 自定义声明落审计，本阶段不消费
    return GovernancePrincipal(
        actor_id=str(actor_id).strip(),
        org_id=str(org_id).strip(),
        actor_kind=actor_kind,
        email=str(email or ""),
        display_name=str(display_name or ""),
        roles=tuple(str(r) for r in roles),
        permissions=frozenset(permissions),
        authenticated_via=authenticated_via,
        issued_at=int(issued_at or 0),
        expires_at=int(expires_at or 0),
    )


__all__ = ["ActorKind", "GovernancePrincipal", "build_principal"]
