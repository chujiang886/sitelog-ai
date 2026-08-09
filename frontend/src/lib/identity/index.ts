/**
 * Phase 3.8.27 T3 —— 企业身份认证接入层统一出口。
 *
 * 页面只 import 本模块，不直接依赖任何具体适配器：
 *
 *     import { getIdentityProvider, requirePermission } from "@/lib/identity";
 *
 *     const provider = getIdentityProvider();
 *     const identity = await provider.getIdentity();      // fail-closed
 *     requirePermission(identity, "governance:review:confirm");
 *     const headers = await provider.getAuthHeaders();
 *
 * 【3.8.28 交付边界更新】JWT 验签、RBAC 真实角色源已在后端落地，
 * 前端缺省走 ``backend-session``：凭据来自登录，主体来自 ``GET /governance/me``。
 * 仍属后续范畴的是 SSO/OIDC 回调与网关模式的真实部署确认。
 */

export {
  IdentityError,
  IdentityInsecureEnvironmentError,
  IdentityNotHumanError,
  IdentityPermissionDeniedError,
  IdentityProviderNotConfiguredError,
  IdentityRedLineViolationError,
  IdentityUnauthenticatedError,
} from "@/lib/identity/errors";

export {
  ROLE_PERMISSIONS,
  assertHumanIdentity,
  assertNoForbiddenPermission,
  assertNoLegacyIdentityHeaders,
  hasPermission,
  normalizePermissions,
  permissionsFromRoles,
  requirePermission,
  toGovernanceHeaders,
} from "@/lib/identity/guards";

export { BackendSessionIdentityProvider } from "@/lib/identity/providers/backend-session";
export { GatewayHeaderIdentityProvider } from "@/lib/identity/providers/gateway-header";
export { JwtIdentityProvider, decodeJwtPayload } from "@/lib/identity/providers/jwt";
export { StaticDevIdentityProvider } from "@/lib/identity/providers/static-dev";

export {
  GOVERNANCE_TOKEN_KEY,
  clearGovernanceToken,
  readGovernanceToken,
  sessionTokenSource,
  writeGovernanceToken,
} from "@/lib/identity/token-store";

export {
  getIdentityProvider,
  resetIdentityProvider,
  resolveIdentityProvider,
  setIdentityProvider,
  type IdentityProviderId,
  type ResolveOptions,
} from "@/lib/identity/registry";

export {
  ALL_GOVERNANCE_PERMISSIONS,
  FORBIDDEN_PERMISSION_PATTERNS,
  LEGACY_IDENTITY_HEADERS,
  type ActorKind,
  type AuthScheme,
  type GovernanceIdentity,
  type GovernancePermission,
  type IdentityProvider,
  type RawActorClaims,
} from "@/lib/identity/types";
