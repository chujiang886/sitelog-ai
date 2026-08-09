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

import { IdentityInsecureEnvironmentError } from "@/lib/identity/errors";
import { assertHumanIdentity, toActorHeaders } from "@/lib/identity/guards";
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

  constructor(options: StaticDevProviderOptions = {}) {
    this.actorId = options.actorId?.trim() || DEFAULT_ACTOR_ID;
    this.displayName = options.displayName?.trim() || this.actorId;
    this.orgId = options.orgId?.trim() || undefined;
    this.roles = options.roles ?? DEFAULT_ROLES;
    this.nodeEnv = options.nodeEnv ?? process.env.NODE_ENV ?? "development";
    this.allowInProduction = options.allowInProduction ?? false;
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

  async getAuthHeaders(): Promise<Readonly<Record<string, string>>> {
    return toActorHeaders(await this.getIdentity());
  }
}
