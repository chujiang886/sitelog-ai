/**
 * Phase 3.8.28 T3(c) —— 后端会话适配器（**生产默认路径**）。
 *
 * ## 与 3.8.27 三个骨架适配器的根本差别
 *
 * 那三个（static-dev / jwt / gateway-header）都在**前端自己回答"我是谁"**：
 * 常量写死、解 JWT payload、读网关头。前端的答案再怎么谨慎也只是一个声明，
 * 而 3.8.28 的核心结论恰恰是 —— 声明不是身份。
 *
 * 本适配器只做一件事：拿着凭据去问后端 ``GET /governance/me``，
 * 把**后端算出来的**主体当作唯一答案。于是：
 *
 *   - actor_id / org_id 来自数据库里的真实用户，不是 token 里的旧快照；
 *   - roles / permissions 是后端每次请求重算的结果（resolver 回权威源重读），
 *     一个人的治理角色被撤销后，刷新页面立刻反映，不必等 token 过期；
 *   - 前端那张 ROLE_PERMISSIONS 表在这条路径上**不参与计算**，
 *     只在其它适配器（离线/网关）里兜底，从根上消除前后端词表漂移。
 *
 * ## 仍然保留 assertHumanIdentity 的原因
 *
 * 后端已经判过一遍 human/红线，这里再判一次不是不信任后端，而是**不信任
 * 这条 HTTP 响应**：任何能改写响应体的中间环节（错配的反代、被污染的缓存、
 * 本地 mock 忘了拆）都可能递回一个非人类主体。多一次本地断言的成本是几微秒，
 * 收益是这类事故会立刻炸在最近的位置，而不是变成一条署名可疑的审计记录。
 *
 * ## 渲染 ≠ 授权
 *
 * 本适配器产出的 permissions 只用于决定按钮灰不灰。后端对每个治理请求独立
 * 判权，前端就算被人改成"全部权限"，也一个动作都做不成。
 */

import {
  IdentityError,
  IdentityNotHumanError,
  IdentityProviderNotConfiguredError,
  IdentityUnauthenticatedError,
} from "@/lib/identity/errors";
import {
  assertHumanIdentity,
  toGovernanceHeaders,
} from "@/lib/identity/guards";
import type { TokenSource } from "@/lib/identity/providers/jwt";
import type {
  ActorKind,
  AuthScheme,
  GovernanceIdentity,
  IdentityProvider,
  RawActorClaims,
} from "@/lib/identity/types";

/** 便于测试注入；缺省用全局 fetch。 */
export type FetchLike = (
  input: string,
  init?: { readonly headers?: Record<string, string> }
) => Promise<{
  readonly ok: boolean;
  readonly status: number;
  json(): Promise<unknown>;
  text(): Promise<string>;
}>;

export interface BackendSessionProviderOptions {
  /** access token 来源。未提供即视为"未配置"（fail-closed）。 */
  readonly tokenSource?: TokenSource;
  /** 后端基址，缺省读 NEXT_PUBLIC_API_BASE_URL。 */
  readonly baseUrl?: string;
  /** 身份端点路径。 */
  readonly mePath?: string;
  /** 注入 fetch（测试用）。 */
  readonly fetchImpl?: FetchLike;
  /** 凭据被后端判定失效时的回调（通常用于清除本地 token）。 */
  readonly onCredentialRejected?: () => void;
}

/** ``GET /governance/me`` 的响应结构（对应 principal.to_public_dict()）。 */
interface MeResponse {
  readonly actor_id?: unknown;
  readonly actor_kind?: unknown;
  readonly org_id?: unknown;
  readonly email?: unknown;
  readonly display_name?: unknown;
  readonly roles?: unknown;
  readonly governance_roles?: unknown;
  readonly permissions?: unknown;
  readonly authenticated_via?: unknown;
  readonly expires_at?: unknown;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function strList(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

export class BackendSessionIdentityProvider implements IdentityProvider {
  readonly id = "backend-session";
  /** 凭据形态仍是 Bearer JWT，审计里的 authenticated_via 由后端给出。 */
  readonly scheme: AuthScheme = "jwt";

  private readonly tokenSource?: TokenSource;
  private readonly baseUrl: string;
  private readonly mePath: string;
  private readonly fetchImpl?: FetchLike;
  private readonly onCredentialRejected?: () => void;

  /** 按 token 缓存身份，避免同一次渲染里重复问后端。token 变即失效。 */
  private cache: { token: string; identity: GovernanceIdentity } | null = null;

  constructor(options: BackendSessionProviderOptions = {}) {
    this.tokenSource = options.tokenSource;
    this.baseUrl = (
      options.baseUrl ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000"
    ).replace(/\/+$/, "");
    this.mePath = options.mePath ?? "/governance/me";
    this.fetchImpl = options.fetchImpl;
    this.onCredentialRejected = options.onCredentialRejected;
  }

  get isConfigured(): boolean {
    return typeof this.tokenSource === "function";
  }

  private assertConfigured(): TokenSource {
    if (!this.tokenSource) {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "未注入 tokenSource；请在登录成功后写入凭据，或显式注入 token 来源。"
      );
    }
    return this.tokenSource;
  }

  private async readToken(): Promise<string> {
    const source = this.assertConfigured();
    const token = await source();
    if (!token || !token.trim()) {
      // 未登录不是"配置问题"而是"还没有人"，用 Unauthenticated 更贴切：
      // 页面据此提示去登录，而不是报"系统未配置"吓运维一跳。
      throw new IdentityUnauthenticatedError(
        "本地没有治理凭据（未登录或凭据已被清除）。"
      );
    }
    return token.trim();
  }

  private resolveFetch(): FetchLike {
    if (this.fetchImpl) return this.fetchImpl;
    const globalFetch = (globalThis as { fetch?: unknown }).fetch;
    if (typeof globalFetch !== "function") {
      throw new IdentityProviderNotConfiguredError(
        this.id,
        "运行环境缺少 fetch；请注入 fetchImpl。"
      );
    }
    return globalFetch as unknown as FetchLike;
  }

  /** 拉取权威主体。任何非 2xx 一律不产出身份。 */
  private async fetchPrincipal(token: string): Promise<GovernanceIdentity> {
    const doFetch = this.resolveFetch();
    let response: Awaited<ReturnType<FetchLike>>;
    try {
      response = await doFetch(`${this.baseUrl}${this.mePath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (cause) {
      // 网络不可达时**不给身份**。缓存一个"上次的身份"继续渲染按钮，
      // 会让人以为自己仍有权限，点下去才发现全是失败。
      throw new IdentityUnauthenticatedError(
        `无法连接治理身份端点（${String(cause)}）。`
      );
    }

    if (!response.ok) {
      if (response.status === 401) {
        this.cache = null;
        this.onCredentialRejected?.();
        throw new IdentityUnauthenticatedError(
          "后端拒绝了当前凭据（已失效或被撤销），请重新登录。"
        );
      }
      if (response.status === 403) {
        // /governance/me 只要求认证；403 意味着主体本身被判定不得进入治理链路。
        throw new IdentityNotHumanError("非人类主体或已被治理层拒绝");
      }
      const detail = await response.text().catch(() => "");
      throw new IdentityError(
        `治理身份端点返回 ${response.status}${detail ? `：${detail}` : ""}`
      );
    }

    const body = (await response.json()) as MeResponse;
    const claims: RawActorClaims = {
      actorId: str(body.actor_id) ?? "",
      // 不臆测为 user：后端说是什么就是什么，非 user 由 assertHumanIdentity 拦。
      actorKind: (str(body.actor_kind) ?? "service") as ActorKind,
      displayName: str(body.display_name) ?? str(body.email),
      orgId: str(body.org_id),
      roles: strList(body.roles),
      // 关键：权限直接采信后端计算结果，不用前端角色表二次推导。
      permissions: strList(body.permissions),
      expiresAt:
        typeof body.expires_at === "number" && body.expires_at > 0
          ? body.expires_at * 1000
          : undefined,
      scheme: this.scheme,
    };
    return assertHumanIdentity(claims);
  }

  async getIdentity(): Promise<GovernanceIdentity> {
    const token = await this.readToken();
    if (this.cache && this.cache.token === token) {
      return this.cache.identity;
    }
    const identity = await this.fetchPrincipal(token);
    this.cache = { token, identity };
    return identity;
  }

  /**
   * 治理请求头：凭据 + 组织复述。
   *
   * 注意这里**先取身份再发头**：如果凭据已经失效，调用方拿到的是一个异常，
   * 而不是一组"看起来没问题、打过去必然 401"的请求头。
   */
  async getAuthHeaders(): Promise<Readonly<Record<string, string>>> {
    const token = await this.readToken();
    const identity = await this.getIdentity();
    return {
      Authorization: `Bearer ${token}`,
      ...toGovernanceHeaders(identity),
    };
  }

  async signOut(): Promise<void> {
    this.cache = null;
    this.onCredentialRejected?.();
  }
}
