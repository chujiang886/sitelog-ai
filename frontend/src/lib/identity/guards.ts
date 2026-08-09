/**
 * Phase 3.8.27 T3 —— 身份校验与 RBAC 判定（运行时 fail-closed 闸门）。
 *
 * 这一层是"适配器说的话"与"页面能做的事"之间的唯一通道：
 *   RawActorClaims（不可信声明） --assertHumanIdentity--> GovernanceIdentity（可用于治理）
 *
 * 所有校验只做一件事：**不满足就抛错**。没有任何降级、过滤、兜底分支。
 */

import {
  IdentityNotHumanError,
  IdentityPermissionDeniedError,
  IdentityRedLineViolationError,
  IdentityUnauthenticatedError,
} from "@/lib/identity/errors";
import {
  ALL_GOVERNANCE_PERMISSIONS,
  FORBIDDEN_PERMISSION_PATTERNS,
  type GovernanceIdentity,
  type GovernancePermission,
  type RawActorClaims,
} from "@/lib/identity/types";

/**
 * 企业角色 → 治理权限映射（RBAC 接入位）。
 *
 * 本阶段只给出**默认映射骨架**；真实企业角色体系（AD 组 / SSO 属性 / IAM 角色）
 * 接入时替换此表即可，页面与适配器均不受影响。
 *
 * 注意：即使是 governance-admin，也**没有**任何"自动通过"能力——
 * 最高权限也只是"有资格提交人工研判"，决定权仍在真人手上（红线②）。
 */
export const ROLE_PERMISSIONS: Readonly<
  Record<string, readonly GovernancePermission[]>
> = {
  "governance-admin": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:review:confirm",
    "governance:execution:read",
    "governance:audit:read",
    "governance:summary:read",
  ],
  "governance-reviewer": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:review:confirm",
    "governance:execution:read",
    "governance:summary:read",
  ],
  "governance-auditor": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:execution:read",
    "governance:audit:read",
    "governance:summary:read",
  ],
  "governance-viewer": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:summary:read",
  ],
};

const PERMISSION_SET: ReadonlySet<string> = new Set(ALL_GOVERNANCE_PERMISSIONS);

/**
 * 红线扫描：任何权限串命中禁语片段即整体拒绝。
 *
 * 之所以"整体拒绝"而不是"过滤掉再放行"：
 * 一份包含 auto_approve 的凭证说明签发侧已经错了，
 * 静默清洗会掩盖事故，让错误配置长期存活。
 */
export function assertNoForbiddenPermission(
  permissions: readonly string[]
): void {
  for (const perm of permissions) {
    const normalized = perm.toLowerCase();
    for (const pattern of FORBIDDEN_PERMISSION_PATTERNS) {
      if (normalized.includes(pattern)) {
        throw new IdentityRedLineViolationError(
          `权限声明「${perm}」命中禁语「${pattern}」`
        );
      }
    }
  }
}

/** 过滤出白名单内的合法治理权限（未知权限忽略，禁语在上一步已拒绝）。 */
export function normalizePermissions(
  permissions: readonly string[]
): readonly GovernancePermission[] {
  assertNoForbiddenPermission(permissions);
  const seen = new Set<string>();
  const out: GovernancePermission[] = [];
  for (const perm of permissions) {
    if (PERMISSION_SET.has(perm) && !seen.has(perm)) {
      seen.add(perm);
      out.push(perm as GovernancePermission);
    }
  }
  return out;
}

/** 依据角色推导权限（并集）。角色未知则不授予任何权限（fail-closed）。 */
export function permissionsFromRoles(
  roles: readonly string[]
): readonly GovernancePermission[] {
  const out = new Set<GovernancePermission>();
  for (const role of roles) {
    for (const perm of ROLE_PERMISSIONS[role] ?? []) {
      out.add(perm);
    }
  }
  return Array.from(out);
}

/**
 * 把不可信的 RawActorClaims 收敛为可用于治理动作的 GovernanceIdentity。
 *
 * 校验顺序（任一不过即抛，不继续）：
 *   1. actorId 非空                       —— 审计必须能落到具体的人
 *   2. actorKind === "user"               —— 红线⑥，与后端 require_human_actor 对齐
 *   3. 凭证未过期                          —— 过期身份不得继续操作
 *   4. 权限声明不含禁语                    —— 红线②/③
 *   5. 权限白名单归一（缺省则按角色推导）
 */
export function assertHumanIdentity(
  claims: RawActorClaims,
  now: number = Date.now()
): GovernanceIdentity {
  if (!claims.actorId || !claims.actorId.trim()) {
    throw new IdentityUnauthenticatedError("缺少 actor_id，无法归属治理责任");
  }
  if (claims.actorKind !== "user") {
    throw new IdentityNotHumanError(claims.actorKind);
  }
  if (typeof claims.expiresAt === "number" && claims.expiresAt <= now) {
    throw new IdentityUnauthenticatedError("责任人凭证已过期，请重新登录");
  }

  const roles = claims.roles ?? [];
  const declared = claims.permissions;
  const permissions =
    declared === undefined
      ? permissionsFromRoles(roles)
      : normalizePermissions(declared);

  return {
    ...claims,
    actorKind: "user",
    roles,
    permissions,
  };
}

/** 是否具备某项治理权限。 */
export function hasPermission(
  identity: GovernanceIdentity,
  permission: GovernancePermission
): boolean {
  return identity.permissions.includes(permission);
}

/** 无权限即抛（用于按钮/请求前的硬闸门）。 */
export function requirePermission(
  identity: GovernanceIdentity,
  permission: GovernancePermission
): void {
  if (!hasPermission(identity, permission)) {
    throw new IdentityPermissionDeniedError(identity.actorId, permission);
  }
}

/**
 * 生成治理 API 所需的主体请求头。
 *
 * 只有通过 assertHumanIdentity 的身份才能走到这里，
 * 因此 x-actor-kind 恒为 "user"——前端不存在"伪造成 user"的构造路径。
 */
export function toActorHeaders(
  identity: GovernanceIdentity
): Readonly<Record<string, string>> {
  const headers: Record<string, string> = {
    "x-actor-id": identity.actorId,
    "x-actor-kind": identity.actorKind,
  };
  if (identity.orgId) {
    headers["org_id"] = identity.orgId;
  }
  return headers;
}
