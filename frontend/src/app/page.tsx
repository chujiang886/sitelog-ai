"use client";

/**
 * 产品首页（业务入口）。替换原先的占位页。
 *
 * 不再陈列"占位"指标，而是把三条真实业务链路（上传 / 咨询 / 报告）
 * 直接摆到用户面前，并反映登录状态。所有 AI 结果在正式 LLM 接入前
 * 均标注 pending_verification，此处不编造任何数据指标。
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import type { JSX } from "react";

import { getIdentityProvider, type GovernanceIdentity } from "@/lib/identity";

const FLOWS: ReadonlyArray<{
  href: string;
  title: string;
  desc: string;
  cta: string;
}> = [
  {
    href: "/upload",
    title: "上传图纸",
    desc: "上传阳台 / 窗户现场照片，Vision Agent 先做一步视觉分析。",
    cta: "上传照片",
  },
  {
    href: "/consult",
    title: "AI 咨询",
    desc: "用自然语言描述需求，触发视觉 / 环境 / 设计三 Agent 联合分析。",
    cta: "开始咨询",
  },
  {
    href: "/result",
    title: "分析报告",
    desc: "查看三 Agent 联合方案，下载可交付的 PDF 方案书。",
    cta: "查看报告",
  },
];

export default function HomePage(): JSX.Element {
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);
  const [checked, setChecked] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const me = await getIdentityProvider().getIdentity();
        if (!cancelled) setIdentity(me);
      } catch {
        // 游客态：展示登录入口即可。
      } finally {
        if (!cancelled) setChecked(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="space-y-8">
      <div>
        <p className="text-sm font-medium text-boip-primary-main">
          建筑开口智能设计平台
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-900">
          让每一扇窗，都有据可循
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          BOIP 把视觉、环境、设计三类 AI 能力接到你的真实项目里：上传现场照片、用自然语言描述需求，
          即可生成带待核实标记的方案书。所有 AI 结果均标注 pending_verification，正式 LLM 接入后自动替换。
        </p>
        {checked && identity ? (
          <p className="mt-3 text-sm text-slate-500">
            已登录：{identity.displayName ?? identity.actorId}
          </p>
        ) : checked ? (
          <Link
            href="/login"
            className="mt-3 inline-block rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white"
          >
            登录后开始
          </Link>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {FLOWS.map((flow) => (
          <Link
            key={flow.href}
            href={flow.href}
            className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-boip-primary-main"
          >
            <h2 className="text-lg font-semibold text-slate-900">{flow.title}</h2>
            <p className="mt-2 text-sm text-slate-500">{flow.desc}</p>
            <span className="mt-4 inline-block text-sm font-medium text-boip-primary-main group-hover:underline">
              {flow.cta} →
            </span>
          </Link>
        ))}
      </div>

      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
          更多
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <Link
            href="/projects"
            className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700"
          >
            项目
          </Link>
          <Link
            href="/knowledge"
            className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700"
          >
            知识库
          </Link>
          <Link
            href="/agents"
            className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700"
          >
            Agent
          </Link>
        </div>
      </div>
    </section>
  );
}
