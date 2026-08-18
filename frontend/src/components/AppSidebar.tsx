"use client";

/**
 * 侧边栏业务导航。替换原先的「侧边栏占位」。
 *
 * 列出产品真实业务入口；有治理权限时追加「治理后台」分组。
 * 身份通过后端会话适配器取得（与 AppUserMenu 共享缓存，二次取极廉价），
 * 取不到时只渲染业务区，不暴露治理入口。
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import type { JSX } from "react";

import { getIdentityProvider, type GovernanceIdentity } from "@/lib/identity";

interface NavLink {
  href: string;
  label: string;
}

const BUSINESS_LINKS: readonly NavLink[] = [
  { href: "/", label: "首页" },
  { href: "/upload", label: "上传图纸" },
  { href: "/consult", label: "AI 咨询" },
  { href: "/result", label: "分析报告" },
  { href: "/projects", label: "项目" },
  { href: "/knowledge", label: "知识库" },
  { href: "/agents", label: "Agent" },
];

export default function AppSidebar(): JSX.Element {
  const [hasGovernance, setHasGovernance] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await getIdentityProvider().getIdentity();
        if (!cancelled) setHasGovernance(me.permissions.length > 0);
      } catch {
        // 游客态：不显示治理入口。
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <nav aria-label="侧边栏业务导航" className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
          业务
        </p>
        <ul className="mt-3 space-y-1">
          {BUSINESS_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="block rounded-md px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50 hover:text-boip-primary-main"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {hasGovernance ? (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            治理
          </p>
          <ul className="mt-3 space-y-1">
            <li>
              <Link
                href="/governance-dashboard"
                className="block rounded-md px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50 hover:text-boip-primary-main"
              >
                治理驾驶舱
              </Link>
            </li>
          </ul>
        </div>
      ) : null}
    </nav>
  );
}
