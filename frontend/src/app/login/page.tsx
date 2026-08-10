"use client";

/**
 * 治理登录页（3.8.28 T3(c) 建立；**3.8.29 T1 迁移到 HttpOnly Cookie**）。
 *
 * 这一页存在的意义只有一句话：**让审计里的名字变成真人的名字**。
 *
 * 3.8.26/3.8.27 的治理驾驶舱靠**写死的常量身份**充当责任人，
 * 于是"谁确认的"这个问题在系统里没有答案。现在它的答案来自这里：
 *   邮箱+密码 → 后端种下 HttpOnly 凭据 Cookie → /governance/me 反算主体 → 渲染。
 *
 * ## 3.8.29 的关键变化：本页不再经手凭据
 *
 * 旧版把响应体里的 ``access_token`` 写进 sessionStorage，等于让 JS 保管治理
 * 凭据 —— 页面上任何一处 XSS 都能把它读走。现在凭据由后端以
 * ``Set-Cookie: boip_access_token; HttpOnly`` 下发，**JS 读不到也写不了**：
 *
 *   - 登录请求必须带 ``credentials: "include"``，否则浏览器不收 Set-Cookie，
 *     表现为"登录返回 200 但随后一直 401"；
 *   - 响应体里仍有 ``access_token``（留给非浏览器客户端走 Bearer），
 *     本页**刻意不读它**，读了就等于把刚关上的口子重新打开；
 *   - 登出必须调后端 ``POST /api/auth/logout``（带 CSRF 头）下发过期 Cookie。
 *     前端自己清状态只是"看起来登出了"，服务端会话依然有效。
 *
 * 三个刻意的克制（沿用）：
 *   1. 本页**不解析 token**，不从 payload 里读角色。登录成功只代表"服务端认了"，
 *      "这个人有什么治理权限"一律由后端回答，前端复述。
 *   2. 登录失败不区分"用户不存在"与"密码错误"（后端已统一文案）。
 *   3. 登录成功后**不自动跳转**到治理驾驶舱，先把后端返回的身份摆出来让人确认
 *      是不是自己 —— 共用电脑上"以为是自己其实是同事"的账号误用，
 *      在治理场景里等同于责任错记。
 */

import Link from "next/link";
import { useState } from "react";

import {
  csrfHeaders,
  getIdentityProvider,
  resetIdentityProvider,
  type GovernanceIdentity,
} from "@/lib/identity";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function LoginPage(): JSX.Element {
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);

  /** 调后端登出端点，让服务端下发过期 Cookie；失败不阻断本地状态复位。 */
  const revokeServerSession = async (): Promise<void> => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { ...csrfHeaders() },
      });
    } catch {
      // 网络不可达时本地照样复位。真正的凭据仍在服务端有效，
      // 这一点由后续请求的 401 兜底，而不是在这里假装成功。
    }
  };

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setIdentity(null);
    // 先清旧会话：登录失败后仍带着上一个人的 Cookie，是最容易出责任事故的状态。
    await revokeServerSession();
    resetIdentityProvider();

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        // 命门：不带 include 浏览器就不收 Set-Cookie，凭据根本没落地。
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        throw new Error(
          res.status === 401
            ? "邮箱或密码不正确。"
            : `登录失败（${res.status}）。`
        );
      }
      // 刻意不读响应体里的 access_token：凭据已在 HttpOnly Cookie 中，
      // 前端再存一份就等于把 XSS 窃取面重新打开。

      // 关键一步：不解析 token，而是带着 Cookie 去问后端"我是谁、我能做什么"。
      // 这里若抛错，说明凭据虽已签发但主体不被治理层接受（停用/非真人），
      // 此时必须把服务端会话也撤掉，不能让页面停在"半登录"状态。
      const me = await getIdentityProvider().getIdentity();
      setIdentity(me);
    } catch (e) {
      await revokeServerSession();
      resetIdentityProvider();
      setError(e instanceof Error ? e.message : "登录失败。");
    } finally {
      setBusy(false);
    }
  };

  const signOut = async (): Promise<void> => {
    await revokeServerSession();
    resetIdentityProvider();
    setIdentity(null);
  };

  const hasGovernanceAccess =
    identity !== null && identity.permissions.length > 0;

  return (
    <section className="mx-auto max-w-md px-6 py-10">
      <p className="text-sm font-medium text-boip-primary-main">身份验证</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">登录</h1>
      <p className="mt-2 text-sm text-slate-500">
        治理动作必须归属到真实责任人。登录后你的每一次确认都会以本人名义写入审计。
      </p>

      {identity === null ? (
        <form
          onSubmit={(e) => void submit(e)}
          className="mt-6 space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label className="block text-sm font-medium text-slate-700">
            邮箱
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="you@example.com"
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            密码
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "登录中…" : "登录"}
          </button>
          <p className="text-xs text-slate-400">
            凭据由服务端以 HttpOnly Cookie 下发，页面脚本无法读取；退出登录时由服务端撤销。
          </p>
        </form>
      ) : (
        <div className="mt-6 space-y-3 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-700">
            已登录为
            <span className="font-semibold">
              {" "}
              {identity.displayName ?? identity.actorId}{" "}
            </span>
            （{identity.actorId}）
          </p>
          <p className="text-xs text-slate-500">
            组织 {identity.orgId ?? "—"} · 身份来源 {identity.scheme}
          </p>
          <p className="text-xs text-slate-500">
            治理角色：
            {identity.roles && identity.roles.length > 0
              ? identity.roles.join("、")
              : "无"}
          </p>

          {hasGovernanceAccess ? (
            <p className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
              已获得 {identity.permissions.length} 项治理权限（由后端判定，前端仅展示）。
            </p>
          ) : (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
              该账号没有任何治理权限。可以浏览，但所有治理动作都会被后端拒绝。
            </p>
          )}

          <div className="flex gap-3 pt-1">
            <Link
              href="/governance-dashboard"
              className="rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white"
            >
              进入治理驾驶舱
            </Link>
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600"
            >
              不是我，退出
            </button>
          </div>
        </div>
      )}

      {error ? (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
    </section>
  );
}
