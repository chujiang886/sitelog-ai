"""FastAPI 依赖装配（Phase 3.8.28 T1/T3）。

治理路由**只应**从这里取身份。所有 ``IdentityError`` 在此统一翻译成 HTTP
状态码，路由自身不再写任何身份判断逻辑 —— 判断散落在路由里正是
Phase 3.8.26 留下 ``require_user`` 头信任的原因。
"""

from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_get_db
from app.identity.errors import (
    IdentityConfigError,
    IdentityCrossOrgError,
    IdentityError,
    IdentityHeaderForgeryError,
    IdentityNotHumanError,
    IdentityPermissionDeniedError,
    IdentityRedLineViolationError,
    IdentitySubjectInactiveError,
    IdentityTokenExpiredError,
    IdentityTokenInvalidError,
    IdentityUnauthenticatedError,
)
from app.identity.permissions import GovernancePermission
from app.identity.principal import GovernancePrincipal
from app.identity.resolver import DbBackedPrincipalResolver
from app.identity.service import IdentityAuthenticationService
from app.identity.verifier import JwtTokenVerifier

#: 已废止的身份请求头。Phase 3.8.28 之前它们**就是**身份来源。
LEGACY_IDENTITY_HEADERS: tuple[str, ...] = ("x-actor-id", "x-actor-kind")

#: 异常 → HTTP 状态码。集中一处，避免各路由自行决定"这算 401 还是 403"。
_STATUS_BY_ERROR: tuple[tuple[type[IdentityError], int], ...] = (
    # 顺序敏感：子类必须排在父类之前。
    (IdentityHeaderForgeryError, 400),
    (IdentityConfigError, 500),
    (IdentityTokenExpiredError, 401),
    (IdentityTokenInvalidError, 401),
    (IdentityUnauthenticatedError, 401),
    (IdentitySubjectInactiveError, 401),
    (IdentityNotHumanError, 403),
    (IdentityRedLineViolationError, 403),
    (IdentityPermissionDeniedError, 403),
    (IdentityCrossOrgError, 403),
)


def http_status_for(error: IdentityError) -> int:
    """把身份异常翻译成 HTTP 状态码；未知身份异常一律 403（fail-closed）。"""

    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return 403


def as_http_exception(error: IdentityError) -> HTTPException:
    return HTTPException(status_code=http_status_for(error), detail=str(error))


# --------------------------------------------------------------------------- #
# 服务装配                                                                      #
# --------------------------------------------------------------------------- #


def build_identity_service(db: AsyncSession) -> IdentityAuthenticationService:
    """生产装配：HS256 JWT + 数据库权威解析。

    OIDC / SSO 骨架**不在此注册**。注册一个必然抛 ``IdentityConfigError`` 的
    验证器，只会让 ``schemes`` 看起来支持三种方式而实际只有一种，给运维制造
    错误预期。等它们真正实装时再挂上来。
    """

    return IdentityAuthenticationService(
        verifiers={"jwt": JwtTokenVerifier()},
        resolver=DbBackedPrincipalResolver(db),
        default_scheme="jwt",
    )


def get_identity_service(
    db: AsyncSession = Depends(async_get_db),
) -> IdentityAuthenticationService:
    return build_identity_service(db)


# --------------------------------------------------------------------------- #
# 主体依赖                                                                      #
# --------------------------------------------------------------------------- #


def assert_no_legacy_identity_headers(
    x_actor_id: str | None, x_actor_kind: str | None
) -> None:
    """携带已废止身份头即报错（不静默忽略）。

    静默忽略在功能上是安全的（我们本来就不读它们），但在**运维语义**上很危险：
    调用方会以为自己成功指定了责任人。治理系统里"我以为我记的是张三，实际记的
    是李四"属于责任错置，比直接失败严重得多。
    """

    present = [
        name
        for name, value in zip(LEGACY_IDENTITY_HEADERS, (x_actor_id, x_actor_kind))
        if value is not None
    ]
    if present:
        raise IdentityHeaderForgeryError(
            f"请求携带了已废止的身份请求头 {present}。"
            "自 Phase 3.8.28 起，治理身份一律由后端从 Bearer 凭据派生，"
            "请求头无法指定责任人；请改用 Authorization: Bearer <token>。"
        )


async def get_current_principal(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_actor_id: Annotated[str | None, Header(alias="x-actor-id")] = None,
    x_actor_kind: Annotated[str | None, Header(alias="x-actor-kind")] = None,
    service: IdentityAuthenticationService = Depends(get_identity_service),
) -> GovernancePrincipal:
    """治理主体依赖 —— 治理路由取身份的唯一入口。"""

    try:
        assert_no_legacy_identity_headers(x_actor_id, x_actor_kind)
        return await service.authenticate(authorization)
    except IdentityError as exc:
        raise as_http_exception(exc) from exc


def require_governance_permission(
    permission: GovernancePermission,
) -> Callable[..., object]:
    """依赖工厂：要求主体持有指定治理权限，否则 403（默认拒绝）。

    用法::

        principal: GovernancePrincipal = Depends(
            require_governance_permission(GovernancePermission.WORKFLOW_READ)
        )
    """

    async def _dependency(
        principal: GovernancePrincipal = Depends(get_current_principal),
    ) -> GovernancePrincipal:
        if not principal.has(permission):
            raise as_http_exception(
                IdentityPermissionDeniedError(
                    f"责任人 {principal.actor_id} 缺少治理权限 "
                    f"{permission.value!r}；当前治理角色："
                    f"{list(principal.governance_roles()) or '无'}。"
                )
            )
        return principal

    return _dependency


def require_same_org(principal: GovernancePrincipal, requested_org: str) -> str:
    """校验请求组织与主体归属一致；不一致抛 403。

    调用方**不应**再从请求头取 org —— 组织由主体携带。本函数存在只是为了
    兜住路径参数/查询串里出现组织标识的场景（例如管理员按组织筛选）。
    """

    target = str(requested_org or "").strip()
    if not target:
        return principal.org_id
    if target != principal.org_id:
        raise as_http_exception(
            IdentityCrossOrgError(
                f"责任人 {principal.actor_id} 归属组织 {principal.org_id}，"
                f"不得访问组织 {target} 的治理事实。"
            )
        )
    return target


__all__ = [
    "LEGACY_IDENTITY_HEADERS",
    "as_http_exception",
    "assert_no_legacy_identity_headers",
    "build_identity_service",
    "get_current_principal",
    "get_identity_service",
    "http_status_for",
    "require_governance_permission",
    "require_same_org",
]
