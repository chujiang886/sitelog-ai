/**
 * Phase 3.8.27 T3 —— JWT 适配器（接入准备骨架，本阶段**不启用**）。
 *
 * 【为什么只做骨架，不做校验】
 * 浏览器侧**没有能力**安全验签：密钥放前端等于公开，验签结果也可被改。
 * 因此本适配器的职责被刻意限定为：
 *   1. 从注入的 token 源取出 access token；
 *   2. 解析 payload 仅用于 UI 展示与本地过期预判（不可信、非安全边界）；
 *   3. 把 Authorization 头透传给后端；
 *   4. **真正的验签、颁发、RBAC 生效点全部在后端**（Phase 3.8.28+ 落地）。
 *
 * 未配置时 getIdentity() 抛 IdentityProviderNotConfiguredError（fail-closed），
 * 绝不退化成匿名或默认责任人。
 *
 * 【后续阶段需补齐（写在这里避免遗忘）】
 *   - 后端新增 JWT 中间件：验签 + 校验 iss/aud/exp + 解析 actor_id/actor_kind/roles；
 *   - 后端 require_user 改为信任中间件解析结果，不再直接信任 x-actor-* 头；
 *   - 前端 tokenSource 接实际登录态（Cookie / SSO 回调 / 刷新令牌）。
 */

import { IdentityProviderNotConfiguredError } from "@/lib/identity/errors";
import { assertHumanIdentity, toActorHeaders } from "@/lib/identity/guards";
import type {
  ActorKind,
  AuthScheme,
  GovernanceIdentity,
  IdentityProvider,
  RawActorClaims,
} from "@/lib/identity/types";

/** token 提供函数；未登录返回 null。 */
export type TokenSource = () => Promise<string | null> | (string | null);

/** claim 字段名映射（不同 IdP 字段名不同，此处可配）。 */
export interface JwtClaimMap {
  readonly actorId: string;
  readonly actorKind: string;
  readonly displayName: string;
  readonly orgId: string;
  readonly roles: string;
}

export interface JwtProviderOptions {
  /** access token 来源。未提供即视为"未配置"。 */
  readonly tokenSource?: TokenSource;
  /** 覆盖部分 claim 字段名。 */
  readonly claimMap?: Partial<JwtClaimMap>;
}

const DEFAULT_CLAIM_MAP: JwtClaimMap = {
  actorId: "sub",
  actorKind: "actor_kind",
  displayName: "name",
  orgId: "org_id",
  roles: "roles",
};

/** base64url 解码 JWT payload。仅用于 UI 展示，**不构成安全判定**。 */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new Error("JWT 结构非法（期望 header.payload.signature）");
  }
  const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  const padded = payload.padEnd(
    payload.length + ((4 - (payload.length % 4)) % 4),
    "="
  );
  const json =
    typeof atob === "function"
      ? atob(padded)
      : Buffer.from(padded, "base64").toString("binary");
  const parsed: unknown = JSON.parse(json);
  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("JWT payload 非对象");
  }
  return parsed as Record<string, unknown>;
}

export class JwtIdentityProvider implements IdentityProvider {
  readonly id = "jwt";
  readonly scheme: AuthScheme = "jwt";

  private readonly tokenSource?: TokenSource;
  private readonly claimMap: JwtClaimMap;

  constructor(options: JwtProviderOptions = {}) {
    this.tokenSource = options.tokenSource;
    this.claimMap = { ...DEFAULT_CLAIM_MAP, ...(options.claimMap ?? {}) };
  }

  get isConfigured(): boolean {
    return typeof this.tokenSource === "function";
  }

  private assertConfigured(): TokenSource {
    if (!this.tokenSource) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "未提供 tokenSource；请在 Phase 3.8.28+ 接入企业登录态后注入 access token 来源。"
      );
    }
    return this.tokenSource;
  }

  private async readToken(): Promise<string> {
    const source = this.assertConfigured();
    const token = await source();
    if (!token) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "tokenSource 返回空 token（未登录）；后端验签中间件尚未落地，禁止放行。"
      );
    }
    return token;
  }

  /** 解析 claims（不可信，仅用于 UI 与本地预判）。 */
  private toClaims(token: string): RawActorClaims {
    const payload = decodeJwtPayload(token);
    const str = (key: string): string | undefined => {
      const v = payload[key];
      return typeof v === "string" && v.trim() ? v : undefined;
    };
    const rawRoles = payload[this.claimMap.roles];
    const roles = Array.isArray(rawRoles)
      ? rawRoles.filter((r): r is string => typeof r === "string")
      : [];
    const exp = payload["exp"];
    return {
      actorId: str(this.claimMap.actorId) ?? "",
      // 缺省不臆测为 user——由 assertHumanIdentity 判定后拒绝（fail-closed）。
      actorKind: (str(this.claimMap.actorKind) ?? "service") as ActorKind,
      displayName: str(this.claimMap.displayName),
      orgId: str(this.claimMap.orgId),
      roles,
      expiresAt: typeof exp === "number" ? exp * 1000 : undefined,
      scheme: this.scheme,
    };
  }

  async getIdentity(): Promise<GovernanceIdentity> {
    return assertHumanIdentity(this.toClaims(await this.readToken()));
  }

  async getAuthHeaders(): Promise<Readonly<Record<string, string>>> {
    const token = await this.readToken();
    const identity = assertHumanIdentity(this.toClaims(token));
    return {
      ...toActorHeaders(identity),
      Authorization: `Bearer ${token}`,
    };
  }
}
