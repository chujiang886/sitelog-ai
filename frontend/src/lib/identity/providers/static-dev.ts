/**
 * Phase 3.8.27 T3 —— static-dev 适配器（开发/演示用固定责任人）。
 *
 * 这是 3.8.26 硬编码 ACTOR_HEADERS 的**唯一合法归宿**：
 * 行为等价（默认仍是 governor-1 / user），但从"页面里的常量"变成
 * "一个显式声明自己只能用于开发环境的适配器实现"。
 *
 * 与旧写法的三点本质差异：
 *   1. 生产环境直接抛错（IdentityInsecureEnvironmentError），不再可能悄悄上线；
 *   2. 责任人可经 env 覆盖，联调时能换人，审计里是真实的人；
 *   3. 与 JWT / SSO 走同一个端口，未来替换零改页面。
 */

import {
  IdentityInsecureEnvironmentError,
  IdentityProviderNotConfiguredError,
} from "@/lib/identity/errors";
import {
  assertHumanIdentity,
  toGovernanceHeaders,
} from "@/lib/identity/guards";
import type {
  AuthScheme,
  GovernanceIdentity,
  IdentityProvider,
} from "@/lib/identity/types";

export interface StaticDevProviderOptions {
  readonly actorId?: string;
  readonly displayName?: string;
  readonly orgId?: string;
  readonly roles?: readonly string[];
  /** 运行环境；生产环境禁止使用本适配器。 */
  readonly nodeEnv?: string;
  /** 显式放行开关（仅用于测试断言场景）。 */
  readonly allowInProduction?: boolean;
  /**
   * 开发态凭据（可选）。
   *
   * 3.8.28 起后端只认 Bearer 凭据，一个"固定责任人"没有凭据就调不通治理接口。
   * 本地联调时可把 ``POST /api/auth/login`` 拿到的真实 token 传进来，
   * 页面便能以这个人的名义走通完整链路；不传则 ``getAuthHeaders()`` 抛错。
   */
  readonly devToken?: string;
}

const DEFAULT_ACTOR_ID = "governor-1";
const DEFAULT_ROLES: readonly string[] = ["governance-reviewer"];

export class StaticDevIdentityProvider implements IdentityProvider {
  readonly id = "static-dev";
  readonly scheme: AuthScheme = "static-dev";

  private readonly actorId: string;
  private readonly displayName: string;
  private readonly orgId?: string;
  private readonly roles: readonly string[];
  private readonly nodeEnv: string;
  private readonly allowInProduction: boolean;
  private readonly devToken?: string;

  constructor(options: StaticDevProviderOptions = {}) {
    this.actorId = options.actorId?.trim() || DEFAULT_ACTOR_ID;
    this.displayName = options.displayName?.trim() || this.actorId;
    this.orgId = options.orgId?.trim() || undefined;
    this.roles = options.roles ?? DEFAULT_ROLES;
    this.nodeEnv = options.nodeEnv ?? process.env.NODE_ENV ?? "development";
    this.allowInProduction = options.allowInProduction ?? false;
    this.devToken = options.devToken?.trim() || undefined;
  }

  /** 固定责任人天然"已配置"，但是否**允许使用**由环境决定。 */
  get isConfigured(): boolean {
    return true;
  }

  /** 生产环境使用固定责任人属于治理事故，直接拒绝。 */
  private assertEnvironmentAllowed(): void {
    if (this.nodeEnv === "production" && !this.allowInProduction) {
      throw new IdentityInsecureEnvironmentError(this.id);
    }
  }

  async getIdentity(): Promise<GovernanceIdentity> {
    this.assertEnvironmentAllowed();
    return assertHumanIdentity({
      actorId: this.actorId,
      actorKind: "user",
      displayName: this.displayName,
      orgId: this.orgId,
      roles: this.roles,
      scheme: this.scheme,
    });
  }

  /**
   * 【3.8.28 行为变更】没有凭据就发不出治理请求头。
   *
   * 旧实现把 ``x-actor-id: governor-1`` 当身份发出去 —— 那正是本阶段修掉的漏洞：
   * 请求头即身份。现在后端见到这两个头直接 400，见不到 Bearer 直接 401。
   *
   * 与其返回一组注定失败的头、让人在 Network 面板里排查半天，
   * 不如在这里就说清楚：固定责任人只能用于渲染，行动需要真实凭据。
   */
  async getAuthHeaders(): Promise<Readonly<Record<string, string>>> {
    const identity = await this.getIdentity();
    if (!this.devToken) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "固定责任人没有可用凭据：治理接口自 Phase 3.8.28 起只接受 Bearer 凭据，" +
          "请改用 backend-session 适配器登录，或为本适配器注入 devToken。"
      );
    }
    return {
      Authorization: `Bearer ${this.devToken}`,
      ...toGovernanceHeaders(identity),
    };
  }
}
