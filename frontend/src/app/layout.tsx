import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "BOIP",
  description: "建筑开口智能设计平台",
};

interface RootLayoutProps {
  children: ReactNode;
}

const navigationItems: Array<{ href: string; label: string }> = [
  { href: "/", label: "首页" },
  { href: "/projects", label: "项目" },
  { href: "/knowledge", label: "知识库" },
  { href: "/agents", label: "Agent" },
];

export default function RootLayout({ children }: RootLayoutProps): JSX.Element {
  return (
    <html lang="zh-CN">
      <body>
        <div className="min-h-screen bg-slate-50">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
              <Link href="/" className="text-lg font-semibold text-boip-primary-main">BOIP</Link>
              <nav aria-label="主导航" className="flex gap-5 text-sm text-slate-600">
                {navigationItems.map((item) => (
                  <Link key={item.href} href={item.href} className="transition hover:text-boip-primary-main">
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
          </header>
          <div className="mx-auto flex max-w-7xl">
            <aside className="hidden min-h-[calc(100vh-65px)] w-56 border-r border-slate-200 bg-white p-5 lg:block">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-400">工作台</p>
              <p className="mt-3 text-sm text-slate-500">侧边栏占位</p>
            </aside>
            <main className="min-w-0 flex-1 px-6 py-10">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
