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
  LEGACY_IDENTITY_HEADERS,
  type GovernanceIdentity,
  type GovernancePermission,
  type RawActorClaims,
} from "@/lib/identity/types";

/**
 * 企业角色 → 治理权限映射。
 *
 * 【这张表只用于渲染，不产生授权效力】
 * 后端对每个请求独立判权，前端算错了顶多是按钮该亮没亮（或该灰没灰），
 * 不会放行任何越权动作。之所以仍要求它与后端逐项一致，是因为**灰错了
 * 会骗人**：团队会以为某个动作被管住了，而实际管没管住取决于后端。
 *
 * 对应后端 ``GOVERNANCE_ROLE_PERMISSIONS``（``app/identity/permissions.py``），
 * 由词表对齐用例钉死。注意两处刻意的不对称，改动前先理解原因：
 *   - admin 与 reviewer 只差 ``audit:read``；
 *   - auditor 有 ``audit:read`` 但**没有**任何写权限。
 * 审计者看得见一切却不能下判断，判断者能下判断却看不到全量审计 ——
 * 防止同一个人既做判断、又掌握对自己判断的审计视角。
 *
 * 即使是 governance-admin 也**没有**任何"自动通过"能力：最高权限也只是
 * "有资格提交人工研判"，决定权仍在真人手上（红线②）。
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
    "governance:workflow:report",
    "governance:execution:submit",
    "governance:workflow:close",
    "governance:release:read",
    "governance:release:signoff",
  ],
  "governance-reviewer": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:review:confirm",
    "governance:execution:read",
    "governance:summary:read",
    "governance:workflow:report",
    "governance:execution:submit",
    "governance:workflow:close",
    "governance:release:read",
  ],
  "governance-auditor": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:execution:read",
    "governance:audit:read",
    "governance:summary:read",
    "governance:release:read",
  ],
  "governance-viewer": [
    "governance:workflow:read",
    "governance:review:read",
    "governance:summary:read",
    "governance:release:read",
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
 * 生成治理 API 的非凭据请求头。
 *
 * 【3.8.28 取代了 toActorHeaders】旧函数发的是 ``x-actor-id`` /
 * ``x-actor-kind``，那两个头**就是**当时的身份来源 —— 也就是那个漏洞本身。
 * 现在身份只能来自 Bearer 凭据，前端连"声明自己是谁"的字段都不该有。
 *
 * 这里唯一剩下的头是 ``org-id``，而且它**不是**在指定组织：后端以主体
 * 携带的组织为准，请求里的值只被允许"复述"（对不上直接 403）。保留它是
 * 为了让越权尝试在服务端留下明确痕迹，而不是让前端自己去猜该访问谁的数据。
 */
export function toGovernanceHeaders(
  identity: GovernanceIdentity
): Readonly<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (identity.orgId) {
    // 注意是连字符：后端 Header(alias="org-id")，下划线版本会被静默忽略。
    headers["org-id"] = identity.orgId;
  }
  return headers;
}

/**
 * 断言一组请求头里不含已废止的身份头（回归哨兵）。
 *
 * 前端只要还在发这两个头，整条治理链路会全线 400。与其等联调时才发现，
 * 不如在构造请求头的位置就炸掉。
 */
export function assertNoLegacyIdentityHeaders(
  headers: Readonly<Record<string, string>>
): void {
  const lowered = Object.keys(headers).map((k) => k.toLowerCase());
  const offenders = LEGACY_IDENTITY_HEADERS.filter((h) => lowered.includes(h));
  if (offenders.length > 0) {
    throw new IdentityRedLineViolationError(
      `请求头包含已废止的身份头 ${offenders.join(" / ")}：` +
        "自 Phase 3.8.28 起治理身份只能来自 Bearer 凭据，请求头无法指定责任人。"
    );
  }
}
