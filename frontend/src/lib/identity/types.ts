/**
 * Phase 3.8.27 T3 —— 企业身份认证接入准备：核心契约（类型层）。
 *
 * 【本文件解决的架构债】
 * 3.8.26 治理驾驶舱把责任人写死在页面里：
 *     const ACTOR_HEADERS = { "x-actor-id": "governor-1", "x-actor-kind": "user" };
 * 后果：
 *   1. 责任人不可换 —— 任何真实企业都不可能只有一个 governor-1；
 *   2. 责任无法追溯 —— 审计里记的是常量，不是真人；
 *   3. 没有接入位 —— 未来 JWT / RBAC / SSO 无处落地，只能改页面；
 *   4. 生产事故面 —— 常量身份一旦带上生产环境，等于"人工确认"形同虚设。
 *
 * 【本阶段范围】只做**接口抽象**（依赖倒置），不实现真实鉴权：
 *   页面 → IdentityProvider（端口） → 具体适配器（static-dev / jwt / sso-oidc）
 * 页面自此只依赖端口，永远不再持有任何硬编码身份。
 *
 * 【红线映射（fail-closed）】
 *   红线①  不改变 AI 治理边界：身份层只描述"谁在操作"，绝不描述"是否批准"。
 *   红线②  禁止 AI 自动审批：GovernancePermission 里**不存在**任何 auto_* 权限，
 *          且 FORBIDDEN_PERMISSION_PATTERNS 在运行时拒绝伪造权限（对齐 Python 侧
 *          _RedLineForbiddenMixin 的 __getattr__ 拦截）。
 *   红线③  禁止 AI 自动执行：身份层不提供任何执行入口，只产出请求头。
 *   红线④  禁止 AI 修改知识：身份层无写能力。
 *   红线⑥  Human-in-the-loop：治理身份在**类型层**被收窄为 actorKind: "user"，
 *          非人类主体在编译期就无法构造出 GovernanceIdentity；
 *          运行期再由 assertHumanIdentity() 二次拦截（双保险）。
 */

/**
 * 主体类型。与后端 ``AuditActorKind`` / ``x-actor-kind`` 同源。
 *
 * 注意：这是**原始声明**（可能来自不可信来源），不代表已获授权。
 */
export type ActorKind = "user" | "agent" | "system" | "service";

/** 身份来源方案。新增鉴权方式时在此扩展，页面无需改动。 */
export type AuthScheme =
  | "static-dev" // 本地开发/演示：显式配置的固定责任人（生产禁用）
  | "jwt" // 企业 JWT（Bearer）
  | "sso-oidc" // 企业 SSO（OIDC / SAML 网关）
  | "gateway-header"; // 由可信网关在边缘注入身份头

/**
 * 治理权限（RBAC 接入位）。
 *
 * 【刻意为之】此联合类型中**没有**、也永远不得添加下列语义：
 *   auto_approve / auto_confirm / auto_execute / auto_close / bypass_human ...
 * 治理动作的"批准"永远来自真人点击 + 后端 require_human_actor，
 * 不来自一个可以被授予的权限位。授权 ≠ 代替人做决定。
 */
export type GovernancePermission =
  | "governance:workflow:read"
  | "governance:review:read"
  | "governance:review:confirm" // 有权"提交"人工研判，不等于自动通过
  | "governance:execution:read"
  | "governance:audit:read"
  | "governance:summary:read"
  | "governance:workflow:report"
  | "governance:execution:submit"
  | "governance:workflow:close"
  // Phase 3.9.2：发布闸门与证据包（只读查看 / 真实人工签署，无 AI 批准位）
  | "governance:release:read"
  | "governance:release:signoff"; // 真实人工签署自己的 GO/NO-GO/NEED_MORE_EVIDENCE

/**
 * 全部合法权限（运行时白名单，用于校验适配器返回值）。
 *
 * 【必须与后端逐字一致】对应 ``backend/app/identity/permissions.py`` 的
 * ``GovernancePermission``。3.8.27 时这里只有 6 项，后端 3.8.28 落地了 9 项，
 * 3.9.2 又扩展 2 项（release:read / release:signoff）—— 共 11 项。
 *
 * 词表对不上会产生两种故障，后一种更危险：
 *   - 前端算出"能点"、后端判"不能做" → 按钮亮着却永远失败，运维只能靠猜；
 *   - 前端算出"不能点"把按钮灰掉，团队据此以为该动作被管住了，而后端因为
 *     词表对不上根本没挂校验 → **权限在视觉上存在，在执行上缺席**。
 *
 * 由 ``backend/tests/test_governance_identity_security.py`` 的词表对齐用例钉死：
 * 改了任何一侧而不改另一侧，后端测试直接失败。
 */
export const ALL_GOVERNANCE_PERMISSIONS: readonly GovernancePermission[] = [
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
] as const;

/**
 * 已废止的身份请求头（Phase 3.8.28 起后端一律 400）。
 *
 * 保留这个常量不是为了使用它，是为了**能断言它不再被发出**：
 * 3.8.27 的 ``toActorHeaders`` 就是靠这两个头充当身份，前端只要还在发，
 * 整条治理链路就会全线 400。测试用它做回归哨兵。
 */
export const LEGACY_IDENTITY_HEADERS: readonly string[] = [
  "x-actor-id",
  "x-actor-kind",
] as const;

/**
 * 禁止出现在权限集合中的语义片段（红线②/③，fail-closed 黑名单）。
 *
 * 即便未来白名单被误扩展，只要命中这些片段就在运行时抛错——
 * 与 Python 侧 ``_REPOSITORY_FORBIDDEN`` / ``_WORKFLOW_FORBIDDEN`` 同一防御思路。
 */
export const FORBIDDEN_PERMISSION_PATTERNS: readonly string[] = [
  "auto_approve",
  "auto-approve",
  "autoapprove",
  "auto_confirm",
  "auto-confirm",
  "auto_execute",
  "auto-execute",
  "auto_close",
  "auto-close",
  "auto_review",
  "auto-review",
  "bypass_human",
  "bypass-human",
  "skip_review",
  "skip-review",
  "skip_human",
  "skip-human",
  "without_human",
  "no_human",
  "ai_approve",
  "ai-approve",
  "agent_approve",
  "self_approve",
  "engineering_approved",
  "engineering_enabled",
] as const;

/**
 * 适配器返回的**原始**主体声明（未经授权校验，可能不是人）。
 *
 * 适配器（尤其是 JWT / SSO）只负责把外部凭证解析成这个结构；
 * "能不能做治理动作"由 assertHumanIdentity() 判定，不由适配器自己说了算。
 */
export interface RawActorClaims {
  /** 主体唯一标识，写入 x-actor-id 与后端审计。 */
  readonly actorId: string;
  /** 主体类型声明。非 "user" 一律不得进入治理写路径。 */
  readonly actorKind: ActorKind;
  /** 展示名（UI 用，不参与鉴权）。 */
  readonly displayName?: string;
  /** 组织 id，用于后端多租户隔离头 org_id。 */
  readonly orgId?: string;
  /** 企业角色（RBAC 原料，由适配器从 JWT claim / SSO 属性映射而来）。 */
  readonly roles?: readonly string[];
  /** 已授予的治理权限。缺省时由 registry 依据角色映射推导。 */
  readonly permissions?: readonly string[];
  /** 凭证过期时间（epoch 毫秒）。过期身份不可用于治理动作。 */
  readonly expiresAt?: number;
  /** 身份来源方案，便于审计与排障。 */
  readonly scheme: AuthScheme;
}

/**
 * 已通过人类校验的治理身份。
 *
 * ``actorKind`` 在类型层被收窄为字面量 "user"：
 * 这意味着任何 agent / system / service 主体**在编译期**就无法被当作治理身份传递，
 * 这是红线⑥ 在前端的类型级落地。
 */
export interface GovernanceIdentity extends RawActorClaims {
  readonly actorKind: "user";
  readonly permissions: readonly GovernancePermission[];
}

/**
 * 身份提供者端口（Port）。
 *
 * 页面/服务只依赖此接口；具体从哪来（常量 / JWT / SSO / 网关头）由适配器决定。
 * 新增鉴权方式 = 新增一个实现 + 在 registry 注册，**页面零改动**。
 */
export interface IdentityProvider {
  /** 适配器 id，用于 registry 选择与审计标注。 */
  readonly id: string;
  /** 身份来源方案。 */
  readonly scheme: AuthScheme;
  /**
   * 适配器是否已完成配置。
   * 未配置时 getIdentity() 必须抛 IdentityProviderNotConfiguredError（fail-closed），
   * **不得**退化为匿名身份或默认责任人。
   */
  readonly isConfigured: boolean;

  /**
   * 取当前治理身份。
   *
   * 契约（所有适配器必须遵守）：
   *   - 未配置        → 抛 IdentityProviderNotConfiguredError
   *   - 未登录/已过期 → 抛 IdentityUnauthenticatedError
   *   - 非人类主体    → 抛 IdentityNotHumanError（红线⑥）
   *   - 绝不返回 null / 匿名兜底身份
   */
  getIdentity(): Promise<GovernanceIdentity>;

  /**
   * 取用于调用治理 API 的请求头。
   *
   * 【3.8.28 契约变更】只允许返回**凭据**（``Authorization: Bearer …``）。
   * 严禁再返回 x-actor-id / x-actor-kind —— 身份由后端从凭据派生，
   * 请求头无法指定责任人，带上旧头后端直接 400。
   *
   * 换句话说：适配器不再"告诉后端我是谁"，只负责"把凭据递过去"。
   */
  getAuthHeaders(): Promise<Readonly<Record<string, string>>>;

  /** 可选：登出（清理本地凭证）。static-dev 无需实现。 */
  signOut?(): Promise<void>;
}
