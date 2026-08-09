/**
 * Phase 3.8.27 T3 —— 身份适配器注册表（唯一装配点）。
 *
 * 页面只调 ``getIdentityProvider()``，永远不 new 具体适配器；
 * 切换鉴权方式 = 改一个环境变量，前端代码零改动。
 *
 * 选择规则（NEXT_PUBLIC_IDENTITY_PROVIDER）：
 *   "static-dev"（缺省）  开发/演示固定责任人；生产环境使用时抛错
 *   "jwt"                 企业 JWT（需注入 tokenSource，Phase 3.8.28+）
 *   "gateway-header"      可信网关注入（需 SSR claimsSource + 部署确认）
 *
 * fail-closed 约定：
 *   - 未知取值 → 抛错，不静默回退到 static-dev；
 *   - 生产环境未显式配置 → 抛错，不允许"默认责任人"上生产。
 */

import {
  IdentityInsecureEnvironmentError,
  IdentityProviderNotConfiguredError,
} from "@/lib/identity/errors";
import { GatewayHeaderIdentityProvider } from "@/lib/identity/providers/gateway-header";
import {
  JwtIdentityProvider,
  type TokenSource,
} from "@/lib/identity/providers/jwt";
import { StaticDevIdentityProvider } from "@/lib/identity/providers/static-dev";
import type { IdentityProvider } from "@/lib/identity/types";

export type IdentityProviderId = "static-dev" | "jwt" | "gateway-header";

const KNOWN_PROVIDER_IDS: readonly IdentityProviderId[] = [
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
  /** JWT 适配器的 token 来源（Phase 3.8.28+ 由登录态注入）。 */
  readonly tokenSource?: TokenSource;
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
    // 未显式配置：开发环境用固定责任人；生产环境一律拒绝（红线⑥）。
    if (nodeEnv === "production") {
      throw new IdentityInsecureEnvironmentError("static-dev");
    }
    return buildStaticDev(options, nodeEnv);
  }

  if (!KNOWN_PROVIDER_IDS.includes(providerId as IdentityProviderId)) {
    throw new IdentityProviderNotConfiguredError(
      providerId,
      `未知的身份适配器；可选值：${KNOWN_PROVIDER_IDS.join(" / ")}`
    );
  }

  switch (providerId as IdentityProviderId) {
    case "static-dev":
      return buildStaticDev(options, nodeEnv);
    case "jwt":
      return new JwtIdentityProvider({ tokenSource: options.tokenSource });
    case "gateway-header":
      return new GatewayHeaderIdentityProvider();
  }
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
