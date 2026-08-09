/**
 * Phase 3.8.27 T3/T5 —— 企业身份适配层测试（fail-closed 全覆盖）。
 *
 * 测试意图不是"覆盖率"，而是把红线钉死：
 *   - 非人类主体永远拿不到治理身份（红线⑥）
 *   - 任何 auto_* 权限声明一律整体拒绝（红线②/③）
 *   - 未配置的适配器绝不降级为默认责任人（fail-closed）
 *   - static-dev 绝不可能出现在生产环境
 *   - 页面拿到的请求头恒为 x-actor-kind=user
 */

import {
  GatewayHeaderIdentityProvider,
  IdentityInsecureEnvironmentError,
  IdentityNotHumanError,
  IdentityPermissionDeniedError,
  IdentityProviderNotConfiguredError,
  IdentityRedLineViolationError,
  IdentityUnauthenticatedError,
  JwtIdentityProvider,
  StaticDevIdentityProvider,
  assertHumanIdentity,
  assertNoForbiddenPermission,
  getIdentityProvider,
  hasPermission,
  normalizePermissions,
  permissionsFromRoles,
  requirePermission,
  resetIdentityProvider,
  resolveIdentityProvider,
  setIdentityProvider,
  toActorHeaders,
  type GovernanceIdentity,
  type RawActorClaims,
} from "@/lib/identity";

const baseClaims: RawActorClaims = {
  actorId: "governor-1",
  actorKind: "user",
  displayName: "张治理",
  orgId: "demo-org",
  roles: ["governance-reviewer"],
  scheme: "static-dev",
};

describe("assertHumanIdentity —— 红线⑥ Human-in-the-loop", () => {
  it("真人主体可通过并推导出角色权限", () => {
    const identity = assertHumanIdentity(baseClaims);
    expect(identity.actorKind).toBe("user");
    expect(identity.actorId).toBe("governor-1");
    expect(identity.permissions).toContain("governance:review:confirm");
    expect(identity.permissions).toContain("governance:workflow:read");
  });

  it.each(["agent", "system", "service"] as const)(
    "非人类主体 %s 一律拒绝",
    (kind) => {
      expect(() =>
        assertHumanIdentity({ ...baseClaims, actorKind: kind })
      ).toThrow(IdentityNotHumanError);
    }
  );

  it("空 actor_id 拒绝（治理责任必须可归属到人）", () => {
    expect(() => assertHumanIdentity({ ...baseClaims, actorId: "   " })).toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("过期凭证拒绝", () => {
    expect(() =>
      assertHumanIdentity({ ...baseClaims, expiresAt: 1_000 }, 2_000)
    ).toThrow(IdentityUnauthenticatedError);
  });

  it("未过期凭证放行", () => {
    const identity = assertHumanIdentity(
      { ...baseClaims, expiresAt: 5_000 },
      2_000
    );
    expect(identity.actorId).toBe("governor-1");
  });

  it("未知角色不授予任何权限（fail-closed，不默认给读权限）", () => {
    const identity = assertHumanIdentity({
      ...baseClaims,
      roles: ["random-role"],
    });
    expect(identity.permissions).toHaveLength(0);
  });
});

describe("权限红线 —— 禁止 AI 自动审批/自动执行（红线②/③）", () => {
  it.each([
    "governance:review:auto_approve",
    "governance:review:auto-confirm",
    "governance:execution:auto_execute",
    "governance:bypass_human",
    "engineering_approved",
    "engineering_enabled",
  ])("权限声明 %s 触发整体拒绝", (perm) => {
    expect(() => assertNoForbiddenPermission([perm])).toThrow(
      IdentityRedLineViolationError
    );
  });

  it("禁语大小写不敏感", () => {
    expect(() =>
      assertNoForbiddenPermission(["Governance:Review:AUTO_APPROVE"])
    ).toThrow(IdentityRedLineViolationError);
  });

  it("含禁语的凭证不做静默过滤，而是拒绝整份身份", () => {
    expect(() =>
      assertHumanIdentity({
        ...baseClaims,
        permissions: ["governance:workflow:read", "governance:auto_approve"],
      })
    ).toThrow(IdentityRedLineViolationError);
  });

  it("白名单外的未知权限被丢弃，不报错也不生效", () => {
    expect(
      normalizePermissions(["governance:workflow:read", "some:other:perm"])
    ).toEqual(["governance:workflow:read"]);
  });

  it("权限去重", () => {
    expect(
      normalizePermissions([
        "governance:workflow:read",
        "governance:workflow:read",
      ])
    ).toEqual(["governance:workflow:read"]);
  });

  it("最高角色 governance-admin 也不具备任何 auto_* 能力", () => {
    const perms = permissionsFromRoles(["governance-admin"]);
    for (const p of perms) {
      expect(p).not.toMatch(/auto|bypass|skip/i);
    }
  });

  it("viewer 角色无提交研判权", () => {
    const identity = assertHumanIdentity({
      ...baseClaims,
      roles: ["governance-viewer"],
    });
    expect(hasPermission(identity, "governance:review:confirm")).toBe(false);
    expect(() =>
      requirePermission(identity, "governance:review:confirm")
    ).toThrow(IdentityPermissionDeniedError);
  });

  it("auditor 可读审计但不可提交研判", () => {
    const identity = assertHumanIdentity({
      ...baseClaims,
      roles: ["governance-auditor"],
    });
    expect(hasPermission(identity, "governance:audit:read")).toBe(true);
    expect(hasPermission(identity, "governance:review:confirm")).toBe(false);
  });
});

describe("toActorHeaders —— 后端 require_user 契约", () => {
  it("恒产出 x-actor-kind=user", () => {
    const headers = toActorHeaders(assertHumanIdentity(baseClaims));
    expect(headers["x-actor-id"]).toBe("governor-1");
    expect(headers["x-actor-kind"]).toBe("user");
    expect(headers["org_id"]).toBe("demo-org");
  });

  it("无 orgId 时不带 org_id 头（由后端取默认租户）", () => {
    const identity = assertHumanIdentity({ ...baseClaims, orgId: undefined });
    expect(toActorHeaders(identity)["org_id"]).toBeUndefined();
  });
});

describe("StaticDevIdentityProvider —— 3.8.26 硬编码身份的合法归宿", () => {
  it("默认行为与 3.8.26 ACTOR_HEADERS 等价（迁移兼容）", async () => {
    const provider = new StaticDevIdentityProvider({ nodeEnv: "development" });
    const headers = await provider.getAuthHeaders();
    expect(headers["x-actor-id"]).toBe("governor-1");
    expect(headers["x-actor-kind"]).toBe("user");
  });

  it("责任人可覆盖（审计里落到真实的人）", async () => {
    const provider = new StaticDevIdentityProvider({
      actorId: "li-si",
      displayName: "李四",
      nodeEnv: "development",
    });
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("li-si");
    expect(identity.displayName).toBe("李四");
  });

  it("生产环境使用固定责任人直接抛错（不可能悄悄上线）", async () => {
    const provider = new StaticDevIdentityProvider({ nodeEnv: "production" });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityInsecureEnvironmentError
    );
    await expect(provider.getAuthHeaders()).rejects.toThrow(
      IdentityInsecureEnvironmentError
    );
  });
});

describe("JwtIdentityProvider —— 接入准备骨架（本阶段不启用）", () => {
  it("未注入 tokenSource 时 isConfigured=false 且 fail-closed", async () => {
    const provider = new JwtIdentityProvider();
    expect(provider.isConfigured).toBe(false);
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("tokenSource 返回空（未登录）时拒绝，不退化为默认责任人", async () => {
    const provider = new JwtIdentityProvider({ tokenSource: () => null });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("token 中 actor_kind 非 user 时拒绝（AI 拿着合法 token 也进不来）", async () => {
    const token = makeJwt({ sub: "svc-bot", actor_kind: "agent" });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    await expect(provider.getIdentity()).rejects.toThrow(IdentityNotHumanError);
  });

  it("token 未声明 actor_kind 时不臆测为 user（默认按 service 拒绝）", async () => {
    const token = makeJwt({ sub: "unknown-1" });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    await expect(provider.getIdentity()).rejects.toThrow(IdentityNotHumanError);
  });

  it("合法人类 token 解析出身份并透传 Authorization", async () => {
    const token = makeJwt({
      sub: "wang-wu",
      actor_kind: "user",
      name: "王五",
      org_id: "org-a",
      roles: ["governance-reviewer"],
    });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("wang-wu");
    expect(identity.scheme).toBe("jwt");
    const headers = await provider.getAuthHeaders();
    expect(headers["Authorization"]).toBe(`Bearer ${token}`);
    expect(headers["x-actor-kind"]).toBe("user");
  });

  it("token 已过期时拒绝", async () => {
    const token = makeJwt({
      sub: "wang-wu",
      actor_kind: "user",
      exp: 1, // 1970 年
    });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("支持自定义 claim 名映射", async () => {
    const token = makeJwt({ uid: "zhao-liu", kind: "user" });
    const provider = new JwtIdentityProvider({
      tokenSource: () => token,
      claimMap: { actorId: "uid", actorKind: "kind" },
    });
    expect((await provider.getIdentity()).actorId).toBe("zhao-liu");
  });
});

describe("GatewayHeaderIdentityProvider —— 部署前提必须显式确认", () => {
  it("未提供 claimsSource 时 fail-closed", async () => {
    const provider = new GatewayHeaderIdentityProvider();
    expect(provider.isConfigured).toBe(false);
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("未确认 gatewayVerified 时拒绝（防身份头被浏览器伪造）", async () => {
    const provider = new GatewayHeaderIdentityProvider({
      claimsSource: () => baseClaims,
    });
    expect(provider.isConfigured).toBe(false);
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("确认部署前提后可用", async () => {
    const provider = new GatewayHeaderIdentityProvider({
      claimsSource: () => baseClaims,
      gatewayVerified: true,
    });
    expect(provider.isConfigured).toBe(true);
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("governor-1");
    expect(identity.scheme).toBe("gateway-header");
  });

  it("网关未注入身份时拒绝", async () => {
    const provider = new GatewayHeaderIdentityProvider({
      claimsSource: () => null,
      gatewayVerified: true,
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });
});

describe("registry —— 唯一装配点", () => {
  afterEach(() => resetIdentityProvider());

  it("开发环境未配置时回落 static-dev", () => {
    const provider = resolveIdentityProvider({ nodeEnv: "development" });
    expect(provider.id).toBe("static-dev");
  });

  it("生产环境未配置时抛错（禁止默认责任人上生产）", () => {
    expect(() => resolveIdentityProvider({ nodeEnv: "production" })).toThrow(
      IdentityInsecureEnvironmentError
    );
  });

  it("未知适配器 id 抛错，不静默回退", () => {
    expect(() =>
      resolveIdentityProvider({ providerId: "magic-auth" })
    ).toThrow(IdentityProviderNotConfiguredError);
  });

  it.each([
    ["jwt", "jwt"],
    ["gateway-header", "gateway-header"],
    ["static-dev", "static-dev"],
  ])("显式指定 %s 得到对应适配器", (id, expected) => {
    const provider = resolveIdentityProvider({
      providerId: id,
      nodeEnv: "development",
    });
    expect(provider.id).toBe(expected);
  });

  it("env 可覆盖责任人与租户", async () => {
    const provider = resolveIdentityProvider({
      providerId: "static-dev",
      nodeEnv: "development",
      actorId: "custom-governor",
      orgId: "org-x",
      roles: ["governance-admin"],
    });
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("custom-governor");
    expect(identity.orgId).toBe("org-x");
    expect(hasPermission(identity, "governance:audit:read")).toBe(true);
  });

  it("单例可注入与重置（SSR / 未来登录态装配）", async () => {
    const fake: GovernanceIdentity = assertHumanIdentity({
      ...baseClaims,
      actorId: "injected-1",
    });
    setIdentityProvider({
      id: "test",
      scheme: "static-dev",
      isConfigured: true,
      getIdentity: async () => fake,
      getAuthHeaders: async () => toActorHeaders(fake),
    });
    expect((await getIdentityProvider().getIdentity()).actorId).toBe(
      "injected-1"
    );
    resetIdentityProvider();
    expect(getIdentityProvider().id).toBe("static-dev");
  });
});

/** 构造一个未签名的测试 JWT（前端本就不验签，签名段仅占位）。 */
function makeJwt(payload: Record<string, unknown>): string {
  const b64 = (obj: Record<string, unknown>): string =>
    Buffer.from(JSON.stringify(obj))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${b64({ alg: "none", typ: "JWT" })}.${b64(payload)}.sig`;
}
