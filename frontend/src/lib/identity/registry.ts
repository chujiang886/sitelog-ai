/**
 * Phase 3.8.27 T3 / 3.8.28 T3(c) —— 身份适配器注册表（唯一装配点）。
 *
 * 页面只调 ``getIdentityProvider()``，永远不 new 具体适配器；
 * 切换鉴权方式 = 改一个环境变量，前端代码零改动。
 *
 * 选择规则（NEXT_PUBLIC_IDENTITY_PROVIDER）：
 *   "backend-session"（缺省）  凭据 + 后端 /governance/me 权威主体（推荐）
 *   "static-dev"               开发/演示固定责任人；生产环境使用时抛错
 *   "jwt"                      前端解 JWT payload（离线/自定义 IdP 试验）
 *   "gateway-header"           可信网关注入（需 SSR claimsSource + 部署确认）
 *
 * 【3.8.28 缺省值变更：static-dev → backend-session】
 * 3.8.27 的缺省是"开发环境给一个固定责任人、生产环境抛错"。这个设计在当时
 * 是合理的（没有真实鉴权可用），但它有个副作用：**开发环境下永远是登录态**，
 * 于是"没登录会怎样"这条分支在日常开发里从来不会被走到，等上了生产才第一次遇见。
 *
 * 现在缺省改为 backend-session：没有凭据就抛 Unauthenticated，页面提示去登录。
 * 开发与生产走同一条路径，差别只是后端地址不同。static-dev 退化为需要**显式
 * 指定**才会启用的逃生舱，且它依然在生产环境抛错。
 *
 * fail-closed 约定：
 *   - 未知取值 → 抛错，不静默回退；
 *   - 缺省路径不再产生任何"默认责任人"，无论什么环境。
 */

import { IdentityProviderNotConfiguredError } from "@/lib/identity/errors";
import { BackendSessionIdentityProvider } from "@/lib/identity/providers/backend-session";
import { GatewayHeaderIdentityProvider } from "@/lib/identity/providers/gateway-header";
import {
  JwtIdentityProvider,
  type TokenSource,
} from "@/lib/identity/providers/jwt";
import { StaticDevIdentityProvider } from "@/lib/identity/providers/static-dev";
import { clearGovernanceToken } from "@/lib/identity/token-store";
import type { IdentityProvider } from "@/lib/identity/types";

export type IdentityProviderId =
  | "backend-session"
  | "static-dev"
  | "jwt"
  | "gateway-header";

const KNOWN_PROVIDER_IDS: readonly IdentityProviderId[] = [
  "backend-session",
  "static-dev",
  "jwt",
  "gateway-header",
];

export interface ResolveOptions {
  /** 覆盖 NEXT_PUBLIC_IDENTITY_PROVIDER（测试用）。 */
  readonly providerId?: string;
  /** 覆盖 NODE_ENV（测试用）。 */
  readonly nodeEnv?: string;
  /** 覆盖 NEXT_PUBLIC_GOVERNANCE_ACTOR_ID（测试用）。 */
  readonly actorId?: string;
  /** 覆盖 NEXT_PUBLIC_GOVERNANCE_ORG_ID（测试用）。 */
  readonly orgId?: string;
  /** 覆盖角色列表（缺省读 NEXT_PUBLIC_GOVERNANCE_ROLES，逗号分隔）。 */
  readonly roles?: readonly string[];
  /**
   * token 来源。**显式注入即切到 bearer 模式**（非浏览器客户端 / E2E）。
   * 不注入时缺省走 cookie 模式，凭据由 HttpOnly Cookie 承载、JS 不经手。
   */
  readonly tokenSource?: TokenSource;
  /** 后端基址覆盖（测试用）。 */
  readonly baseUrl?: string;
}

function readRoles(raw: string | undefined): readonly string[] | undefined {
  if (!raw) return undefined;
  const roles = raw
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);
  return roles.length > 0 ? roles : undefined;
}

/**
 * 构造适配器实例（纯函数，便于测试；不缓存）。
 */
export function resolveIdentityProvider(
  options: ResolveOptions = {}
): IdentityProvider {
  const nodeEnv = options.nodeEnv ?? process.env.NODE_ENV ?? "development";
  const rawId =
    options.providerId ?? process.env.NEXT_PUBLIC_IDENTITY_PROVIDER ?? "";
  const providerId = rawId.trim();

  if (!providerId) {
    // 未显式配置：走真实登录态。没登录就是没登录，任何环境都不发默认责任人。
    return buildBackendSession(options);
  }

  if (!KNOWN_PROVIDER_IDS.includes(providerId as IdentityProviderId)) {
    throw new IdentityProviderNotConfiguredError(
      providerId,
      `未知的身份适配器；可选值：${KNOWN_PROVIDER_IDS.join(" / ")}`
    );
  }

  switch (providerId as IdentityProviderId) {
    case "backend-session":
      return buildBackendSession(options);
    case "static-dev":
      return buildStaticDev(options, nodeEnv);
    case "jwt":
      return new JwtIdentityProvider({ tokenSource: options.tokenSource });
    case "gateway-header":
      return new GatewayHeaderIdentityProvider();
  }
}

function buildBackendSession(
  options: ResolveOptions
): BackendSessionIdentityProvider {
  // 3.8.29：缺省走 cookie 模式（凭据在 HttpOnly Cookie，JS 读不到）。
  // 只有调用方**显式**注入 tokenSource 时才退回 bearer —— 那通常是 E2E
  // 脚本或非浏览器客户端，属于有意为之，不该被缺省值悄悄决定。
  const explicitToken = options.tokenSource;
  return new BackendSessionIdentityProvider({
    credentialMode: explicitToken ? "bearer" : "cookie",
    tokenSource: explicitToken,
    baseUrl: options.baseUrl,
    // 后端判定凭据失效时顺手清掉本地残留，避免用户反复看到同一条 401。
    // cookie 模式下真正的失效由后端下发过期 Set-Cookie 完成，这里只清缓存。
    onCredentialRejected: clearGovernanceToken,
  });
}

function buildStaticDev(
  options: ResolveOptions,
  nodeEnv: string
): StaticDevIdentityProvider {
  return new StaticDevIdentityProvider({
    actorId: options.actorId ?? process.env.NEXT_PUBLIC_GOVERNANCE_ACTOR_ID,
    orgId: options.orgId ?? process.env.NEXT_PUBLIC_GOVERNANCE_ORG_ID,
    roles:
      options.roles ?? readRoles(process.env.NEXT_PUBLIC_GOVERNANCE_ROLES),
    nodeEnv,
    // 本地联调用的真实凭据（可空）。没有它这个适配器只能渲染，不能行动。
    devToken: process.env.NEXT_PUBLIC_GOVERNANCE_DEV_TOKEN,
  });
}

let _cached: IdentityProvider | null = null;

/** 进程内单例（页面统一入口）。测试中用 resetIdentityProvider() 清理。 */
export function getIdentityProvider(): IdentityProvider {
  if (_cached === null) {
    _cached = resolveIdentityProvider();
  }
  return _cached;
}

/** 显式注入适配器（SSR / 测试 / 未来登录态装配用）。 */
export function setIdentityProvider(provider: IdentityProvider): void {
  _cached = provider;
}

/** 清空单例缓存。 */
export function resetIdentityProvider(): void {
  _cached = null;
}
