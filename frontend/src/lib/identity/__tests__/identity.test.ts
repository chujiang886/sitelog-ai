/**
 * Phase 3.8.27 T3/T5 + 3.8.28 T3(c)/T5 —— 企业身份适配层测试（fail-closed 全覆盖）。
 *
 * 测试意图不是"覆盖率"，而是把红线钉死：
 *   - 非人类主体永远拿不到治理身份（红线⑥）
 *   - 任何 auto_* 权限声明一律整体拒绝（红线②/③）
 *   - 未配置的适配器绝不降级为默认责任人（fail-closed）
 *   - static-dev 绝不可能出现在生产环境
 *   - **任何适配器都不得再发出 x-actor-* 身份头**（3.8.28 的核心回归哨兵）
 *   - 治理权限以后端 /governance/me 的判定为准，前端不自行加戏
 */

import {
  ALL_GOVERNANCE_PERMISSIONS,
  BackendSessionIdentityProvider,
  GatewayHeaderIdentityProvider,
  IdentityError,
  IdentityInsecureEnvironmentError,
  IdentityNotHumanError,
  IdentityPermissionDeniedError,
  IdentityProviderNotConfiguredError,
  IdentityRedLineViolationError,
  IdentityUnauthenticatedError,
  JwtIdentityProvider,
  LEGACY_IDENTITY_HEADERS,
  StaticDevIdentityProvider,
  assertHumanIdentity,
  assertNoForbiddenPermission,
  assertNoLegacyIdentityHeaders,
  clearGovernanceToken,
  getIdentityProvider,
  hasPermission,
  normalizePermissions,
  permissionsFromRoles,
  readGovernanceToken,
  requirePermission,
  resetIdentityProvider,
  resolveIdentityProvider,
  setIdentityProvider,
  toGovernanceHeaders,
  writeGovernanceToken,
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

  it("显式给出空权限集时不回退到角色推导（后端说没有就是没有）", () => {
    // 这条区分很要紧：permissions 缺省 = "没人告诉我"，permissions=[] = "后端算过了，是空"。
    // 若两者都回退到前端角色表，一个被撤权的人会在界面上继续看到亮着的按钮。
    const identity = assertHumanIdentity({ ...baseClaims, permissions: [] });
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

  it("权限白名单本身不含任何 auto_* 语义（词表级红线）", () => {
    for (const perm of ALL_GOVERNANCE_PERMISSIONS) {
      expect(perm).not.toMatch(/auto|bypass|skip|approved_by_ai/i);
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

  it("reviewer 有写权限但看不到全量审计（判断者与审计者分离）", () => {
    const identity = assertHumanIdentity({
      ...baseClaims,
      roles: ["governance-reviewer"],
    });
    expect(hasPermission(identity, "governance:workflow:close")).toBe(true);
    expect(hasPermission(identity, "governance:audit:read")).toBe(false);
  });
});

describe("toGovernanceHeaders —— 请求头不再是身份来源（3.8.28 核心）", () => {
  it("只复述组织，不声明责任人", () => {
    const headers = toGovernanceHeaders(assertHumanIdentity(baseClaims));
    expect(headers).toEqual({ "org-id": "demo-org" });
  });

  it("无 orgId 时不带任何头（后端以主体归属为准）", () => {
    const identity = assertHumanIdentity({ ...baseClaims, orgId: undefined });
    expect(toGovernanceHeaders(identity)).toEqual({});
  });

  it.each(LEGACY_IDENTITY_HEADERS)("产出中不含已废止头 %s", (legacy) => {
    const headers = toGovernanceHeaders(assertHumanIdentity(baseClaims));
    expect(Object.keys(headers)).not.toContain(legacy);
  });

  it("org-id 用连字符（后端 Header(alias=\"org-id\")，下划线会被静默忽略）", () => {
    const headers = toGovernanceHeaders(assertHumanIdentity(baseClaims));
    expect(headers["org_id"]).toBeUndefined();
    expect(headers["org-id"]).toBe("demo-org");
  });
});

describe("assertNoLegacyIdentityHeaders —— 回归哨兵", () => {
  it("干净的请求头通过", () => {
    expect(() =>
      assertNoLegacyIdentityHeaders({ Authorization: "Bearer x" })
    ).not.toThrow();
  });

  it.each(LEGACY_IDENTITY_HEADERS)("含 %s 立即抛错", (legacy) => {
    expect(() =>
      assertNoLegacyIdentityHeaders({ [legacy]: "governor-1" })
    ).toThrow(IdentityRedLineViolationError);
  });

  it("大小写变体同样拦截（HTTP 头名不区分大小写）", () => {
    expect(() =>
      assertNoLegacyIdentityHeaders({ "X-Actor-Id": "governor-1" })
    ).toThrow(IdentityRedLineViolationError);
  });
});

describe("StaticDevIdentityProvider —— 3.8.26 硬编码身份的合法归宿", () => {
  it("可用于渲染，但没有凭据就发不出请求头（3.8.28 行为变更）", async () => {
    const provider = new StaticDevIdentityProvider({ nodeEnv: "development" });
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("governor-1");
    await expect(provider.getAuthHeaders()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("注入 devToken 后产出 Bearer 头，且绝不含旧身份头", async () => {
    const provider = new StaticDevIdentityProvider({
      nodeEnv: "development",
      orgId: "org-dev",
      devToken: "dev-token-abc",
    });
    const headers = await provider.getAuthHeaders();
    expect(headers["Authorization"]).toBe("Bearer dev-token-abc");
    expect(headers["org-id"]).toBe("org-dev");
    expect(() => assertNoLegacyIdentityHeaders(headers)).not.toThrow();
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
    const provider = new StaticDevIdentityProvider({
      nodeEnv: "production",
      devToken: "even-with-a-token",
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityInsecureEnvironmentError
    );
    // 有凭据也不行：问题不在于能不能认证，而在于责任人是个常量。
    await expect(provider.getAuthHeaders()).rejects.toThrow(
      IdentityInsecureEnvironmentError
    );
  });
});

describe("JwtIdentityProvider —— 离线/自定义 IdP 路径", () => {
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

  it("组织声明默认读 tenant_id（与后端 JwtTokenVerifier 同源）", async () => {
    const token = makeJwt({
      sub: "wang-wu",
      actor_kind: "user",
      tenant_id: "org-a",
    });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    expect((await provider.getIdentity()).orgId).toBe("org-a");
  });

  it("只透传凭据，不再补发身份头", async () => {
    const token = makeJwt({
      sub: "wang-wu",
      actor_kind: "user",
      name: "王五",
      tenant_id: "org-a",
      roles: ["governance-reviewer"],
    });
    const provider = new JwtIdentityProvider({ tokenSource: () => token });
    const identity = await provider.getIdentity();
    expect(identity.actorId).toBe("wang-wu");
    expect(identity.scheme).toBe("jwt");

    const headers = await provider.getAuthHeaders();
    expect(headers["Authorization"]).toBe(`Bearer ${token}`);
    expect(headers["org-id"]).toBe("org-a");
    expect(() => assertNoLegacyIdentityHeaders(headers)).not.toThrow();
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

describe("BackendSessionIdentityProvider —— 身份由后端回答（生产默认）", () => {
  const ME = {
    actor_id: "11111111-1111-1111-1111-111111111111",
    actor_kind: "user",
    org_id: "org-a",
    email: "gov@example.com",
    display_name: "治理员",
    roles: ["designer", "governance-reviewer"],
    governance_roles: ["governance-reviewer"],
    permissions: ["governance:workflow:read", "governance:review:confirm"],
    authenticated_via: "jwt",
    expires_at: 0,
  };

  const fakeFetch = (
    body: unknown,
    { ok = true, status = 200 }: { ok?: boolean; status?: number } = {}
  ) =>
    jest.fn(async () => ({
      ok,
      status,
      json: async () => body,
      text: async () => JSON.stringify(body),
    }));

  it("未注入 tokenSource 时 fail-closed", async () => {
    const provider = new BackendSessionIdentityProvider();
    expect(provider.isConfigured).toBe(false);
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityProviderNotConfiguredError
    );
  });

  it("没有凭据时报「未登录」而不是「未配置」", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => null,
      fetchImpl: fakeFetch(ME),
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("带 Bearer 调 /governance/me 并采信后端主体", async () => {
    const impl = fakeFetch(ME);
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      baseUrl: "http://api.test",
      fetchImpl: impl,
    });
    const identity = await provider.getIdentity();

    expect(impl).toHaveBeenCalledWith("http://api.test/governance/me", {
      headers: { Authorization: "Bearer tok-1" },
    });
    expect(identity.actorId).toBe(ME.actor_id);
    expect(identity.orgId).toBe("org-a");
    expect(identity.displayName).toBe("治理员");
    expect(identity.permissions).toEqual(ME.permissions);
  });

  it("权限完全来自后端，不被前端角色表放大", async () => {
    // 后端只给了 read；前端角色表里 governance-reviewer 有 8 项权限。
    // 若这里回退到角色推导，界面会亮出 7 个点了必失败的按钮。
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({
        ...ME,
        permissions: ["governance:workflow:read"],
      }),
    });
    const identity = await provider.getIdentity();
    expect(identity.roles).toContain("governance-reviewer");
    expect(identity.permissions).toEqual(["governance:workflow:read"]);
    expect(hasPermission(identity, "governance:review:confirm")).toBe(false);
  });

  it("后端返回空权限时如实反映（登录了但没有治理权）", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({ ...ME, roles: ["designer"], permissions: [] }),
    });
    expect((await provider.getIdentity()).permissions).toHaveLength(0);
  });

  it("后端 401 时清缓存并回调清凭据", async () => {
    const onRejected = jest.fn();
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "stale",
      fetchImpl: fakeFetch({ detail: "expired" }, { ok: false, status: 401 }),
      onCredentialRejected: onRejected,
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
    expect(onRejected).toHaveBeenCalledTimes(1);
  });

  it("后端 403 视为主体不得进入治理链路", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({ detail: "not human" }, { ok: false, status: 403 }),
    });
    await expect(provider.getIdentity()).rejects.toThrow(IdentityNotHumanError);
  });

  it("后端 5xx 不产出身份（不缓存旧身份继续渲染）", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({ detail: "boom" }, { ok: false, status: 500 }),
    });
    await expect(provider.getIdentity()).rejects.toThrow(IdentityError);
  });

  it("网络不可达时抛未认证，绝不静默沿用上一次身份", async () => {
    const impl = jest.fn(async () => {
      throw new Error("ECONNREFUSED");
    });
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: impl as never,
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("响应体被篡改为非人类主体时本地二次拦截（红线⑥）", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({ ...ME, actor_kind: "agent" }),
    });
    await expect(provider.getIdentity()).rejects.toThrow(IdentityNotHumanError);
  });

  it("响应体携带禁语权限时整体拒绝（红线②）", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({
        ...ME,
        permissions: ["governance:review:auto_approve"],
      }),
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityRedLineViolationError
    );
  });

  it("后端给出的过期时间已过时拒绝", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch({ ...ME, expires_at: 1 }), // 1970 年（秒）
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("同一 token 只问一次后端；换 token 立即重问", async () => {
    let token = "tok-1";
    const impl = fakeFetch(ME);
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => token,
      fetchImpl: impl,
    });
    await provider.getIdentity();
    await provider.getIdentity();
    expect(impl).toHaveBeenCalledTimes(1);

    token = "tok-2";
    await provider.getIdentity();
    expect(impl).toHaveBeenCalledTimes(2);
  });

  it("请求头 = 凭据 + 组织复述，绝无身份头", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "tok-1",
      fetchImpl: fakeFetch(ME),
    });
    const headers = await provider.getAuthHeaders();
    expect(headers).toEqual({
      Authorization: "Bearer tok-1",
      "org-id": "org-a",
    });
    expect(() => assertNoLegacyIdentityHeaders(headers)).not.toThrow();
  });

  it("凭据失效时 getAuthHeaders 抛错，而不是给一组注定 401 的头", async () => {
    const provider = new BackendSessionIdentityProvider({
      tokenSource: () => "stale",
      fetchImpl: fakeFetch({}, { ok: false, status: 401 }),
    });
    await expect(provider.getAuthHeaders()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
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

  it("不补发身份头（凭据由网关在边缘注入）", async () => {
    const provider = new GatewayHeaderIdentityProvider({
      claimsSource: () => baseClaims,
      gatewayVerified: true,
    });
    const headers = await provider.getAuthHeaders();
    expect(headers).toEqual({ "org-id": "demo-org" });
    expect(() => assertNoLegacyIdentityHeaders(headers)).not.toThrow();
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

describe("token-store —— 凭据只活在当前标签页", () => {
  afterEach(() => clearGovernanceToken());

  it("写入后可读回", () => {
    writeGovernanceToken("tok-xyz");
    expect(readGovernanceToken()).toBe("tok-xyz");
  });

  it("空串视为登出", () => {
    writeGovernanceToken("tok-xyz");
    writeGovernanceToken("   ");
    expect(readGovernanceToken()).toBeNull();
  });

  it("clear 后读不到", () => {
    writeGovernanceToken("tok-xyz");
    clearGovernanceToken();
    expect(readGovernanceToken()).toBeNull();
  });

  it("凭据不落 localStorage（关标签页即失效）", () => {
    writeGovernanceToken("tok-xyz");
    expect(window.localStorage.length).toBe(0);
  });
});

describe("registry —— 唯一装配点", () => {
  afterEach(() => {
    resetIdentityProvider();
    clearGovernanceToken();
  });

  it("未配置时缺省走后端会话（不再产生默认责任人）", () => {
    const provider = resolveIdentityProvider({ nodeEnv: "development" });
    expect(provider.id).toBe("backend-session");
  });

  it("生产环境缺省同样走后端会话（开发与生产同一条路径）", () => {
    const provider = resolveIdentityProvider({ nodeEnv: "production" });
    expect(provider.id).toBe("backend-session");
  });

  it("缺省适配器在未登录时抛未认证，而不是给个匿名身份", async () => {
    const provider = resolveIdentityProvider({ nodeEnv: "production" });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityUnauthenticatedError
    );
  });

  it("未知适配器 id 抛错，不静默回退", () => {
    expect(() =>
      resolveIdentityProvider({ providerId: "magic-auth" })
    ).toThrow(IdentityProviderNotConfiguredError);
  });

  it.each([
    ["backend-session", "backend-session"],
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

  it("static-dev 仍是显式选择才生效，且生产环境照样拒绝", async () => {
    const provider = resolveIdentityProvider({
      providerId: "static-dev",
      nodeEnv: "production",
    });
    await expect(provider.getIdentity()).rejects.toThrow(
      IdentityInsecureEnvironmentError
    );
  });

  it("env 可覆盖责任人与租户（static-dev 显式路径）", async () => {
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

  it("缺省适配器读 sessionStorage 中的登录凭据", async () => {
    writeGovernanceToken("tok-from-login");
    const provider = resolveIdentityProvider({
      nodeEnv: "development",
      baseUrl: "http://api.test",
    }) as BackendSessionIdentityProvider;
    // 不联网：只验证它确实认为自己已配置且会去读那个 token。
    expect(provider.isConfigured).toBe(true);
    expect(readGovernanceToken()).toBe("tok-from-login");
  });

  it("单例可注入与重置（SSR / 登录态装配）", async () => {
    const fake: GovernanceIdentity = assertHumanIdentity({
      ...baseClaims,
      actorId: "injected-1",
    });
    setIdentityProvider({
      id: "test",
      scheme: "static-dev",
      isConfigured: true,
      getIdentity: async () => fake,
      getAuthHeaders: async () => toGovernanceHeaders(fake),
    });
    expect((await getIdentityProvider().getIdentity()).actorId).toBe(
      "injected-1"
    );
    resetIdentityProvider();
    expect(getIdentityProvider().id).toBe("backend-session");
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
