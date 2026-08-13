"use client";

/**
 * Phase 3.9.7-change —— 生产变更管控平面 · 只读控制台。
 *
 * 设计红线（与后端 agents/enterprise/production_change 同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；请求头由 IdentityProvider 产出。
 * - **无任何真实执行按钮**：本页面不存在 "Deploy / Execute / Rollback Now / Apply / Migrate /
 *   Activate" 入口。真实生产变更 / 部署 / 回滚 / 应用 / 迁移 / 激活一律只能由主理人在**人类终端**执行。
 * - AI 只装配事实与仿真留痕；最终 GO / NO-GO 只能由四角色真人线下签署后由主理人执行。
 * - 顶部恒显示 `engineering_enabled=false`；取不到合法身份时页面不降级，直接禁用一切写入动作。
 */

import { useEffect, useState } from "react";

import {
  getIdentityProvider,
  type GovernanceIdentity,
} from "@/lib/identity";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** 13 个只读 GET 端点（与 backend/app/api/governance_change.py 严格对齐）。 */
const READONLY_PATHS: readonly string[] = [
  "readiness",
  "plan",
  "window",
  "preflight",
  "checkpoint",
  "abort-policy",
  "rollback-reference",
  "post-verification",
  "evidence",
  "simulation",
  "failure-scenarios",
  "package",
  "decision-ledger",
] as const;

interface ChangeResponse {
  engineering_enabled: boolean;
  [k: string]: unknown;
}

interface SectionData {
  path: string;
  title: string;
  data: ChangeResponse | undefined;
  error: string | null;
  loading: boolean;
}

/** 真实执行端点（明确不存在；列出仅作红线提示）。 */
const ABSENT_ENDPOINTS: readonly string[] = [
  "POST /governance/change/execute",
  "POST /governance/change/deploy",
  "POST /governance/change/rollback",
  "POST /governance/change/apply",
  "POST /governance/change/migrate",
  "POST /governance/change/activate",
  "POST /governance/change/trigger-go",
  "POST /governance/change/auto-execute",
];

function ChangeControlSection({
  title,
  data,
  error,
  loading,
}: {
  title: string;
  data: ChangeResponse | undefined;
  error: string | null;
  loading: boolean;
}): JSX.Element {
  const eng = data?.engineering_enabled;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        {eng !== undefined ? (
          <span
            className={`rounded-full px-3 py-0.5 text-xs font-medium ${
              eng === false
                ? "bg-emerald-100 text-emerald-700"
                : "bg-red-100 text-red-700"
            }`}
          >
            engineering_enabled={String(eng)}
          </span>
        ) : null}
      </div>
      {error ? (
        <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </p>
      ) : loading ? (
        <p className="mt-2 text-xs text-slate-400">加载中…</p>
      ) : (
        <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-600">
          {JSON.stringify(data ?? null, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function GovernanceChangePage(): JSX.Element {
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);
  const [sections, setSections] = useState<SectionData[]>(
    READONLY_PATHS.map((p) => ({
      path: p,
      title: p,
      data: undefined,
      error: null,
      loading: false,
    }))
  );
  const [loadingAll, setLoadingAll] = useState<boolean>(false);
  const [globalError, setGlobalError] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const provider = getIdentityProvider();
        const id = await provider.getIdentity();
        if (mounted) setIdentity(id);
      } catch {
        if (mounted) setIdentity(null);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const loadAll = async () => {
    if (!identity) {
      setGlobalError("未取得责任人身份，只读视图已禁用。");
      return;
    }
    setLoadingAll(true);
    setGlobalError("");
    try {
      const provider = getIdentityProvider();
      const headers = await provider.getAuthHeaders();
      const results = await Promise.all(
        READONLY_PATHS.map(async (p) => {
          const res = await fetch(`${API_BASE}/governance/change/${p}`, {
            headers,
          });
          if (!res.ok) {
            return {
              p,
              data: undefined as ChangeResponse | undefined,
              error: `加载失败（${res.status}）`,
            };
          }
          return {
            p,
            data: (await res.json()) as ChangeResponse,
            error: null as string | null,
          };
        })
      );
      setSections((prev) =>
        prev.map((s) => {
          const r = results.find((x) => x.p === s.path);
          return r
            ? { ...s, data: r.data, error: r.error, loading: false }
            : { ...s, loading: false };
        })
      );
    } catch (e) {
      setGlobalError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoadingAll(false);
    }
  };

  useEffect(() => {
    if (identity) void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity]);

  const anyEngEnabled = sections.some((s) => s.data?.engineering_enabled === true);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">
          生产变更管控平面（Phase 3.9.7-change · 只读）
        </h1>
        <button
          type="button"
          onClick={() => void loadAll()}
          disabled={!identity || loadingAll}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
        >
          {loadingAll ? "刷新中…" : "刷新只读材料"}
        </button>
      </header>

      <p className="mt-2 text-sm text-slate-500">
        以下 13 项材料由后端按变更管控层装配，全部为事实、仿真与人工留痕，
        <span className="font-medium">不含任何 AI 裁决、不宣布 GO、不激活</span>。
        真实生产变更 / 部署 / 回滚 / 应用 / 迁移 / 激活只能由主理人在人类终端执行
        （红线①②③④⑤⑨⑩）。
      </p>

      <div
        className={`mt-4 rounded-lg px-4 py-3 text-sm font-medium ${
          anyEngEnabled
            ? "border border-red-200 bg-red-50 text-red-700"
            : "border border-emerald-200 bg-emerald-50 text-emerald-700"
        }`}
      >
        {anyEngEnabled
          ? "警告：检测到 engineering_enabled=true，已超出本平面 BUILT_NO_GO 态。"
          : "当前态：PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO（engineering_enabled=false）。"}
      </div>

      {!identity ? (
        <p className="mt-4 text-sm text-slate-400">未取得责任人身份，只读视图已禁用。</p>
      ) : globalError ? (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {globalError}
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {sections.map((s) => (
            <ChangeControlSection
              key={s.path}
              title={`/governance/change/${s.path}`}
              data={s.data}
              error={s.error}
              loading={s.loading}
            />
          ))}
        </div>
      )}

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-slate-800">
          明确不提供的端点（红线③/⑩）
        </h2>
        <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-slate-500">
          {ABSENT_ENDPOINTS.map((e) => (
            <li key={e} className="font-mono">
              {e}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-slate-400">
          本页面无任何 Deploy / Execute / Rollback Now / Apply / Migrate / Activate 按钮。
          若任一上述端点真实出现，CI 闸门 check_production_change_control_gate.py 须失败。
        </p>
      </section>
    </main>
  );
}
