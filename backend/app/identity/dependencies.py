"""FastAPI 依赖装配（Phase 3.8.28 T1/T3）。

治理路由**只应**从这里取身份。所有 ``IdentityError`` 在此统一翻译成 HTTP
状态码，路由自身不再写任何身份判断逻辑 —— 判断散落在路由里正是
Phase 3.8.26 留下 ``require_user`` 头信任的原因。
"""

from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_cookies import resolve_bearer_credential
from app.core.config import (
    PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS,
    get_settings,
)
from app.core.security_audit import record_security_event
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
from app.identity.verifier import (
    HttpJwksResolver,
    JwtTokenVerifier,
    OidcTokenVerifier,
    SsoGatewayVerifier,
)

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
    """生产装配：按 ``IDENTITY_PROVIDER`` 选择验证器。

    设计原则（T2）：接口标准化、未配置 fail-closed、**绝不**自动降级到开发身份。

    - ``jwt``（默认）：HS256 JWT + 数据库权威解析；
    - ``oidc``：需 issuer / audience / JWKS URL 三点齐全，否则不注册、整体拒绝；
    - ``sso-gateway``：需显式 ``SSO_GATEWAY_TRUSTED=true``，否则不注册。

    生产环境额外红线：``static-dev`` 等逃生舱**禁止**作为生产提供方；
    试图用未配置/被禁的提供方 → 启动即 ``IdentityConfigError``（fail-closed）。
    """

    settings = get_settings()
    provider = (settings.identity_provider or "jwt").strip().lower()

    if settings.is_production:
        if provider in PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS:
            raise IdentityConfigError(
                f"生产环境禁止身份提供方 {provider!r}（仅 {sorted(PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS)} "
                "一类开发逃生舱被禁用）。请在 IDENTITY_PROVIDER 使用 jwt / oidc / sso-gateway。"
            )

    verifiers: dict[str, object] = {}
    if provider == "jwt":
        verifiers["jwt"] = JwtTokenVerifier()
    elif provider == "oidc":
        if not (settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url):
            raise IdentityConfigError(
                "OIDC 提供方未完整配置（需 OIDC_ISSUER / OIDC_AUDIENCE / "
                "OIDC_JWKS_URL 三者齐全），拒绝启动以免降级放行。"
            )
        verifiers["oidc"] = OidcTokenVerifier(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            jwks_resolver=HttpJwksResolver(settings.oidc_jwks_url),
        )
    elif provider == "sso-gateway":
        if not settings.sso_gateway_trusted:
            raise IdentityConfigError(
                "SSO 网关提供方未获部署侧显式信任（SSO_GATEWAY_TRUSTED=true 缺失），"
                "拒绝启动以免伪造网关头绕过身份。"
            )
        verifiers["sso-gateway"] = SsoGatewayVerifier(
            gateway_verified=True, claims_reader=None
        )
    else:
        raise IdentityConfigError(
            f"未知身份提供方 {provider!r}；可选：jwt / oidc / sso-gateway。"
        )

    return IdentityAuthenticationService(
        verifiers=verifiers,  # type: ignore[arg-type]
        resolver=DbBackedPrincipalResolver(db),
        default_scheme=provider,
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
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_actor_id: Annotated[str | None, Header(alias="x-actor-id")] = None,
    x_actor_kind: Annotated[str | None, Header(alias="x-actor-kind")] = None,
    service: IdentityAuthenticationService = Depends(get_identity_service),
    db: AsyncSession = Depends(async_get_db),
) -> GovernancePrincipal:
    """治理主体依赖 —— 治理路由取身份的唯一入口。

    凭据两条通道、**显式 Authorization 头优先，HttpOnly Cookie 兜底**
    （见 ``resolve_bearer_credential``）。Cookie 里是裸 token，会在那里被
    补回 ``Bearer `` 前缀后再交给身份服务，两条通道对下游完全等价。
    """

    try:
        assert_no_legacy_identity_headers(x_actor_id, x_actor_kind)
        credential = resolve_bearer_credential(
            request, authorization, settings=get_settings()
        )
        principal = await service.authenticate(credential)
    except IdentityError as exc:
        # T4：身份校验失败追加审计（不可修改、append-only），再翻译为 HTTP 错误。
        try:
            await record_security_event(
                db,
                action="identity_failure",
                tenant_id=None,
                actor_id=None,
                target_id=type(exc).__name__,
                detail=str(exc)[:500],
            )
        except Exception:  # noqa: BLE001 - 审计写入失败不得影响主错误响应
            pass
        raise as_http_exception(exc) from exc
    return principal


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
        db: AsyncSession = Depends(async_get_db),
    ) -> GovernancePrincipal:
        if not principal.has(permission):
            # T4：权限被拒追加审计（append-only）。
            try:
                await record_security_event(
                    db,
                    action="permission_denied",
                    tenant_id=None,
                    actor_id=None,
                    target_id=principal.actor_id,
                    detail=f"missing={permission.value}",
                )
            except Exception:  # noqa: BLE001
                pass
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
