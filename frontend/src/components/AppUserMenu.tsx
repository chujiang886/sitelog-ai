"use client";

/**
 * 顶部右侧登录 / 用户状态区。
 *
 * 这是「产品真能用起来」的关键一环：导航不再只指向占位页，而是
 * 真实反映当前是否登录、是谁在操作。组件用后端会话身份适配器取
 * 当前主体（凭据在 HttpOnly Cookie 里，JS 读不到），未登录则给出
 * 登录入口；有治理权限时才显示「治理后台」次级入口。
 *
 * 取身份失败（未登录 / 凭据失效）一律降级为游客态，绝不伪造身份。
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import type { JSX } from "react";

import { getIdentityProvider, type GovernanceIdentity } from "@/lib/identity";

export default function AppUserMenu(): JSX.Element {
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);
  const [checked, setChecked] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await getIdentityProvider().getIdentity();
        if (!cancelled) setIdentity(me);
      } catch {
        // 未登录或凭据失效：保持游客态，显示登录入口即可。
      } finally {
        if (!cancelled) setChecked(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!checked) {
    return <span className="text-sm text-slate-400">…</span>;
  }

  if (!identity) {
    return (
      <Link
        href="/login"
        className="rounded-md border border-boip-primary-main px-3 py-1.5 text-sm font-medium text-boip-primary-main transition hover:bg-boip-primary-main hover:text-white"
      >
        登录
      </Link>
    );
  }

  const hasGovernance = identity.permissions.length > 0;

  return (
    <div className="flex items-center gap-3 text-sm">
      {hasGovernance ? (
        <Link
          href="/governance-dashboard"
          className="text-slate-500 transition hover:text-boip-primary-main"
        >
          治理后台
        </Link>
      ) : null}
      <span className="text-slate-700">
        {identity.displayName ?? identity.actorId}
      </span>
    </div>
  );
}
