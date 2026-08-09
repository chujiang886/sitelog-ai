/**
 * Phase 3.8.27 T3 —— 可信网关适配器（接入准备骨架，本阶段**不启用**）。
 *
 * 适用形态：企业已有 SSO/OIDC 网关（如 APISIX / Kong / Nginx+oauth2-proxy），
 * 由网关在边缘完成鉴权后，把身份以请求头形式注入下游。
 *
 * 【关键前提，必须在部署侧保证】
 * 只有当浏览器**无法直接绕过网关**访问后端时，这套方案才成立；
 * 否则任何人都能手工伪造 x-actor-id 头。因此本适配器强制要求显式声明
 * ``gatewayVerified: true``——把这个前提变成一次有意识的确认，而不是默认假设。
 *
 * 未声明 / 未提供 claims 源时 fail-closed 抛错。
 */

import { IdentityProviderNotConfiguredError } from "@/lib/identity/errors";
import {
  assertHumanIdentity,
  toGovernanceHeaders,
} from "@/lib/identity/guards";
import type {
  AuthScheme,
  GovernanceIdentity,
  IdentityProvider,
  RawActorClaims,
} from "@/lib/identity/types";

/** 由 SSR / 路由层从网关注入头解析出的 claims 源。 */
export type GatewayClaimsSource = () =>
  | Promise<RawActorClaims | null>
  | (RawActorClaims | null);

export interface GatewayHeaderProviderOptions {
  readonly claimsSource?: GatewayClaimsSource;
  /**
   * 部署侧确认：后端仅可经由可信网关访问，浏览器无法直连伪造身份头。
   * 未显式置 true 时本适配器拒绝工作。
   */
  readonly gatewayVerified?: boolean;
}

export class GatewayHeaderIdentityProvider implements IdentityProvider {
  readonly id = "gateway-header";
  readonly scheme: AuthScheme = "gateway-header";

  private readonly claimsSource?: GatewayClaimsSource;
  private readonly gatewayVerified: boolean;

  constructor(options: GatewayHeaderProviderOptions = {}) {
    this.claimsSource = options.claimsSource;
    this.gatewayVerified = options.gatewayVerified ?? false;
  }

  get isConfigured(): boolean {
    return typeof this.claimsSource === "function" && this.gatewayVerified;
  }

  private assertConfigured(): GatewayClaimsSource {
    if (!this.claimsSource) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "未提供 claimsSource；需由 SSR 层解析网关注入的身份头后传入。"
      );
    }
    if (!this.gatewayVerified) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "未确认 gatewayVerified；必须先保证后端不可被浏览器直连，否则身份头可被伪造。"
      );
    }
    return this.claimsSource;
  }

  async getIdentity(): Promise<GovernanceIdentity> {
    const source = this.assertConfigured();
    const claims = await source();
    if (!claims) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "网关未注入任何身份信息（可能未经过鉴权入口）。"
      );
    }
    return assertHumanIdentity({ ...claims, scheme: this.scheme });
  }

  /**
   * 网关模式下浏览器**不需要**自己带凭据：凭据由网关在边缘注入。
   *
   * 因此这里只复述组织，绝不补发 ``x-actor-*``。若真让前端补发，等于把
   * "网关已鉴权"这个前提降级成"谁都能声明自己是谁"，本适配器的全部安全性
   * 都建立在浏览器无法绕过网关直连之上（见构造函数的 gatewayVerified 确认）。
   */
  async getAuthHeaders(): Promise<Readonly<Record<string, string>>> {
    return toGovernanceHeaders(await this.getIdentity());
  }
}
