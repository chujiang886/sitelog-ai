"""企业身份认证与 RBAC 治理层（Phase 3.8.28）。

本包解决一个具体缺陷：Phase 3.8.26/27 的治理接口把 ``x-actor-id`` /
``x-actor-kind`` 两个**请求头**当作身份来源，任何人都能伪造出一个"真人责任人"
并完成人工研判确认。六个阶段搭建的 Human-in-the-loop 红线，在传输层是敞开的。

分层：

- ``permissions``  治理权限词表（与前端 3.8.27 同一套）+ 角色映射 + 禁语
- ``verifier``     凭据 → 声明（JWT 启用；OIDC / SSO 骨架）
- ``resolver``     声明 → 主体（回权威源确认仍然有效）
- ``principal``    治理主体（构造即校验，非真人不可构造）
- ``service``      认证编排（唯一链路）
- ``dependencies`` FastAPI 装配 + 异常到 HTTP 的统一翻译
- ``accountability`` 治理动作 → 责任五元组（T4）
- ``seed``         治理 RBAC 目录种子与显式授权（T2）
"""

from app.identity.accountability import (
    ACCOUNTABILITY_CONTEXT_FIELDS,
    ACCOUNTABILITY_FIELDS,
    GOVERNANCE_ACCOUNTABILITY_ACTION,
    accountability_context,
    format_accountability,
    parse_accountability,
    record_accountability,
)
from app.identity.dependencies import (
    LEGACY_IDENTITY_HEADERS,
    build_identity_service,
    get_current_principal,
    get_identity_service,
    require_governance_permission,
    require_same_org,
)
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
from app.identity.permissions import (
    ALL_GOVERNANCE_PERMISSIONS,
    FORBIDDEN_PERMISSION_PATTERNS,
    GOVERNANCE_ROLE_ADMIN,
    GOVERNANCE_ROLE_AUDITOR,
    GOVERNANCE_ROLE_PERMISSIONS,
    GOVERNANCE_ROLE_REVIEWER,
    GOVERNANCE_ROLE_VIEWER,
    GOVERNANCE_ROLES,
    GovernancePermission,
    assert_no_forbidden_permission,
    is_governance_role,
    permissions_for_roles,
)
from app.identity.principal import ActorKind, GovernancePrincipal, build_principal
from app.identity.resolver import (
    ClaimsOnlyPrincipalResolver,
    DbBackedPrincipalResolver,
    PrincipalResolver,
)
from app.identity.seed import assign_governance_role, seed_governance_rbac
from app.identity.service import IdentityAuthenticationService
from app.identity.verifier import (
    JwtTokenVerifier,
    OidcTokenVerifier,
    SsoGatewayVerifier,
    TokenVerifier,
    VerifiedClaims,
)

__all__ = [
    "ACCOUNTABILITY_CONTEXT_FIELDS",
    "ACCOUNTABILITY_FIELDS",
    "ALL_GOVERNANCE_PERMISSIONS",
    "ActorKind",
    "ClaimsOnlyPrincipalResolver",
    "DbBackedPrincipalResolver",
    "FORBIDDEN_PERMISSION_PATTERNS",
    "GOVERNANCE_ACCOUNTABILITY_ACTION",
    "GOVERNANCE_ROLES",
    "GOVERNANCE_ROLE_ADMIN",
    "GOVERNANCE_ROLE_AUDITOR",
    "GOVERNANCE_ROLE_PERMISSIONS",
    "GOVERNANCE_ROLE_REVIEWER",
    "GOVERNANCE_ROLE_VIEWER",
    "GovernancePermission",
    "GovernancePrincipal",
    "IdentityAuthenticationService",
    "IdentityConfigError",
    "IdentityCrossOrgError",
    "IdentityError",
    "IdentityHeaderForgeryError",
    "IdentityNotHumanError",
    "IdentityPermissionDeniedError",
    "IdentityRedLineViolationError",
    "IdentitySubjectInactiveError",
    "IdentityTokenExpiredError",
    "IdentityTokenInvalidError",
    "IdentityUnauthenticatedError",
    "JwtTokenVerifier",
    "LEGACY_IDENTITY_HEADERS",
    "OidcTokenVerifier",
    "PrincipalResolver",
    "SsoGatewayVerifier",
    "TokenVerifier",
    "VerifiedClaims",
    "accountability_context",
    "assert_no_forbidden_permission",
    "assign_governance_role",
    "build_identity_service",
    "build_principal",
    "format_accountability",
    "get_current_principal",
    "get_identity_service",
    "is_governance_role",
    "parse_accountability",
    "permissions_for_roles",
    "record_accountability",
    "require_governance_permission",
    "require_same_org",
    "seed_governance_rbac",
]
