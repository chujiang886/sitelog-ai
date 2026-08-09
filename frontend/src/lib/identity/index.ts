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
 * 本阶段交付边界：**只有接口抽象与 fail-closed 闸门**。
 * JWT 验签、SSO 回调、RBAC 真实角色源均属 Phase 3.8.28+ 范畴。
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
  hasPermission,
  normalizePermissions,
  permissionsFromRoles,
  requirePermission,
  toActorHeaders,
} from "@/lib/identity/guards";

export { GatewayHeaderIdentityProvider } from "@/lib/identity/providers/gateway-header";
export { JwtIdentityProvider, decodeJwtPayload } from "@/lib/identity/providers/jwt";
export { StaticDevIdentityProvider } from "@/lib/identity/providers/static-dev";

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
  type ActorKind,
  type AuthScheme,
  type GovernanceIdentity,
  type GovernancePermission,
  type IdentityProvider,
  type RawActorClaims,
} from "@/lib/identity/types";
