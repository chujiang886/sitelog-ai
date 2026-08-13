"use client";

/**
 * Phase 3.9.8 Task 14 —— 生产激活干跑与人工决策演练控制台（SIMULATION ONLY / NOT PRODUCTION）。
 *
 * 设计红线（与后端 governance_activation_simulation.py 同源，fail-closed）：
 * - 本页面**只**调用隔离模拟端点 /governance/activation/simulation/*；
 *   绝不出现 /activate /deploy-production /go 任何入口（红线①⑤）。
 * - 页面顶部与多处以醒目方式声明：SIMULATION ONLY · NOT PRODUCTION ·
 *   engineering_enabled=false · production_activated=false · real_signoff_count=0。
 * - 所有读/写只驱动隔离沙盒，绝不触碰真实 HumanSignoffRegistry / FinalDecisionLedger /
 *   Evidence Registry / 生产审计命名空间（红线③/④/⑧/⑩）。
 * - 运行（run）按钮只是触发一次干跑并回读报告，不翻转任何真实状态、不部署、不激活。
 */

import { useCallback, useEffect, useState } from "react";

import {
  getIdentityProvider,
  hasPermission,
  requirePermission,
  type GovernanceIdentity,
} from "@/lib/identity";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type Perm = "governance:release:read";

// ---------------------------------------------------------------------
// 类型（宽松，避免与后端字段严格耦合；后端返回原始 dict，未包 ApiResponse）。
// ---------------------------------------------------------------------

interface RedLines {
  production_activated: boolean;
  real_signoff_count: number;
  engineering_enabled: boolean;
}

interface Capability {
  simulation_only: boolean;
  not_production: boolean;
  phase: string;
  description: string;
  endpoints: Record<string, string>;
  forbidden_endpoints: string[];
  red_lines: RedLines;
}

type JsonMap = Record<string, unknown>;

// ---------------------------------------------------------------------
// 取值辅助（安全地把 unknown 转成可渲染类型）。
// ---------------------------------------------------------------------

function asStr(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asBool(v: unknown, fallback = false): boolean {
  return typeof v === "boolean" ? v : fallback;
}
function asList(v: unknown): JsonMap[] {
  return Array.isArray(v) ? (v as JsonMap[]) : [];
}
function asMap(v: unknown): JsonMap {
  return typeof v === "object" && v !== null ? (v as JsonMap) : {};
}

// ---------------------------------------------------------------------
// 鉴权封装：所有请求强制要求真实 USER + RELEASE_READ，并带 CSRF 头。
// ---------------------------------------------------------------------

async function authFetch(path: string, permission: Perm): Promise<JsonMap> {
  const provider = getIdentityProvider();
  const me = await provider.getIdentity(); // fail-closed：取不到身份即抛错
  requirePermission(me, permission);
  const headers = await provider.getAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`请求失败（${res.status}）：${path}`);
  return (await res.json()) as JsonMap;
}

async function authPost(
  path: string,
  permission: Perm,
  body: unknown,
): Promise<JsonMap> {
  const provider = getIdentityProvider();
  const me = await provider.getIdentity();
  requirePermission(me, permission);
  const headers = await provider.getAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`运行失败（${res.status}）${text ? `：${text}` : ""}`);
  }
  return (await res.json()) as JsonMap;
}

// ---------------------------------------------------------------------
// 小红线徽标
// ---------------------------------------------------------------------

function RedLineChip({ label, ok }: { label: string; ok: boolean }): JSX.Element {
  return (
    <span
      className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${
        ok ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
      }`}
    >
      {label}={ok ? "false" : "true"}
    </span>
  );
}

// ---------------------------------------------------------------------
// 页面
// ---------------------------------------------------------------------

export default function GovernanceSimulationPage(): JSX.Element {
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);

  const [capability, setCapability] = useState<Capability | null>(null);
  const [scenarios, setScenarios] = useState<JsonMap[]>([]);
  const [negativePaths, setNegativePaths] = useState<JsonMap[]>([]);

  const [loadingStatic, setLoadingStatic] = useState(false);
  const [staticError, setStaticError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runSimId, setRunSimId] = useState<string | null>(null);
  const [runReport, setRunReport] = useState<JsonMap | null>(null);

  const [reportIdInput, setReportIdInput] = useState("");
  const [reportById, setReportById] = useState<JsonMap | null>(null);
  const [reportByIdError, setReportByIdError] = useState<string | null>(null);

  const canRead =
    identity !== null && hasPermission(identity, "governance:release:read");

  // 1) 鉴权：取身份 + 权限校验（fail-closed；取不到或不具备权限则禁用一切）。
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const provider = getIdentityProvider();
        const me = await provider.getIdentity();
        if (!hasPermission(me, "governance:release:read")) {
          throw new Error("当前身份不具备 governance:release:read 权限，无法进入模拟控制台");
        }
        if (active) {
          setIdentity(me);
          setIdentityError(null);
        }
      } catch (e) {
        if (active) {
          setIdentity(null);
          setIdentityError(e instanceof Error ? e.message : "身份校验失败");
        }
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // 2) 加载静态模拟数据（capability / scenarios / negative-paths）。
  const loadStatic = useCallback(async () => {
    if (!canRead) return;
    setLoadingStatic(true);
    setStaticError(null);
    try {
      const [cap, scn, neg] = await Promise.all([
        authFetch("/governance/activation/simulation/", "governance:release:read"),
        authFetch("/governance/activation/simulation/scenarios", "governance:release:read"),
        authFetch("/governance/activation/simulation/negative-paths", "governance:release:read"),
      ]);
      setCapability(cap as unknown as Capability);
      setScenarios(asList(scn["scenarios"]));
      setNegativePaths(asList(neg["negative_paths"]));
    } catch (e) {
      setStaticError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoadingStatic(false);
    }
  }, [canRead]);

  useEffect(() => {
    if (canRead) void loadStatic();
  }, [canRead, loadStatic]);

  // 3) 运行一次完整干跑（只驱动隔离沙盒）。
  const runDryRun = useCallback(async () => {
    if (!canRead) return;
    setRunning(true);
    setRunError(null);
    try {
      const res = await authPost(
        "/governance/activation/simulation/run",
        "governance:release:read",
        { candidate_id: "RC-3.9.8-SIM", scenario: "production_activation_full_dry_run" },
      );
      setRunSimId(asStr(res["simulation_id"]));
      setRunReport(asMap(res["report"]));
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "运行失败");
    } finally {
      setRunning(false);
    }
  }, [canRead]);

  // 4) 按 id 读取历史干跑报告。
  const fetchReportById = useCallback(async () => {
    if (!canRead || !reportIdInput.trim()) return;
    setReportByIdError(null);
    try {
      const res = await authFetch(
        `/governance/activation/simulation/report/${encodeURIComponent(reportIdInput.trim())}`,
        "governance:release:read",
      );
      setReportById(asMap(res["report"]));
    } catch (e) {
      setReportById(null);
      setReportByIdError(e instanceof Error ? e.message : "读取失败");
    }
  }, [canRead, reportIdInput]);

  const redLines: RedLines | null = capability?.red_lines ?? null;

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-8">
      {/* 顶部醒目横幅：SIMULATION ONLY · NOT PRODUCTION */}
      <div className="sticky top-0 z-10 mb-6 rounded-xl border border-red-300 bg-red-50 px-5 py-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-md bg-red-600 px-3 py-1 text-sm font-bold text-white">
            SIMULATION ONLY
          </span>
          <span className="rounded-md bg-red-600 px-3 py-1 text-sm font-bold text-white">
            NOT PRODUCTION
          </span>
          <span className="text-sm font-semibold text-red-800">
            生产激活干跑与人工决策演练控制台（Phase 3.9.8）
          </span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-red-700">
          本控制台只驱动隔离沙盒，不触发真实激活、不翻转 engineering_enabled、不部署、不写真实
          控制平面。以下红线状态必须恒为 false / 0：
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <RedLineChip label="engineering_enabled" ok={redLines ? redLines.engineering_enabled === false : true} />
          <RedLineChip label="production_activated" ok={redLines ? redLines.production_activated === false : true} />
          <RedLineChip label="real_signoff_count" ok={redLines ? redLines.real_signoff_count === 0 : true} />
        </div>
      </div>

      {/* 身份门禁失败 */}
      {identityError !== null ? (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          ⛔ {identityError}（本控制台不降级，已禁用一切写入与读取动作。）
        </div>
      ) : null}

      {canRead ? (
        <div className="space-y-6">
          {/* 能力说明 */}
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-800">能力说明（capability）</h2>
            {capability ? (
              <div className="mt-3 space-y-3 text-sm text-slate-600">
                <p>
                  <span className="font-medium text-slate-700">simulation_only：</span>
                  {String(capability.simulation_only)}
                  <span className="ml-3 font-medium text-slate-700">not_production：</span>
                  {String(capability.not_production)}
                  <span className="ml-3 font-medium text-slate-700">phase：</span>
                  {asStr(capability.phase)}
                </p>
                <p className="text-slate-600">{asStr(capability.description)}</p>
                <div>
                  <p className="font-medium text-slate-700">禁止端点（明确不存在）：</p>
                  <ul className="mt-1 list-inside list-disc space-y-1 text-red-700">
                    {asList(capability.forbidden_endpoints).map((ep, i) => (
                      <li key={i}>{asStr(ep)}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                {loadingStatic ? "加载中…" : "尚未加载。"}
              </p>
            )}
          </section>

          {staticError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              ⚠️ 静态数据加载失败：{staticError}
            </div>
          ) : null}

          {/* 场景矩阵（14） */}
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-800">
                合成决策场景矩阵（{scenarios.length} 个）
              </h2>
              <button
                onClick={() => void loadStatic()}
                disabled={loadingStatic}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 disabled:opacity-50"
              >
                {loadingStatic ? "刷新中…" : "刷新"}
              </button>
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              {scenarios.map((s, i) => (
                <div key={i} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                  <p className="text-sm font-semibold text-slate-800">{asStr(s["title"]) || asStr(s["scenario_id"])}</p>
                  <p className="mt-1 text-xs text-slate-500">{asStr(s["scenario_id"])}</p>
                  <p className="mt-1 text-xs text-slate-600">{asStr(s["description"])}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 font-medium text-blue-700">
                      期望结论：{asStr(s["expected_outcome"])}
                    </span>
                    {asBool(s["inject_engineering_enabled_true"]) ? (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-700">
                        注入 engineering_enabled=true（应被拒）
                      </span>
                    ) : null}
                    {asBool(s["evidence_drift"]) ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
                        证据漂移
                      </span>
                    ) : null}
                    {asBool(s["signoff_conflict"]) ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
                        签署冲突
                      </span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 负路径矩阵（12） */}
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-800">
              负路径验证矩阵（{negativePaths.length} 条，应全部 rejected=true）
            </h2>
            <div className="mt-3 space-y-2">
              {negativePaths.map((n, i) => {
                const rejected = asBool(n["rejected"]);
                return (
                  <div
                    key={i}
                    className="flex items-start justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-800">{asStr(n["title"])}</p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {asStr(n["path_id"])} — {asStr(n["description"])}
                      </p>
                      {asStr(n["detail"]) ? (
                        <p className="mt-0.5 text-xs text-slate-400">细节：{asStr(n["detail"])}</p>
                      ) : null}
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
                        rejected ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                      }`}
                    >
                      {rejected ? "已拦截 (rejected)" : "未拦截（缺陷）"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* 运行干跑 */}
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-800">运行一次完整干跑（run）</h2>
              <button
                onClick={() => void runDryRun()}
                disabled={running}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {running ? "运行中…" : "▶ 运行干跑"}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              仅触发隔离沙盒的一次完整干跑并回读报告；不翻转任何真实状态、不部署、不激活。
            </p>
            {runError ? (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
                ⚠️ {runError}
              </div>
            ) : null}
            {runSimId ? (
              <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
                <p className="text-sm font-medium text-slate-800">
                  simulation_id：<span className="font-mono">{runSimId}</span>
                </p>
                {runReport ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <RedLineChip
                      label="engineering_enabled"
                      ok={asBool(runReport["engineering_enabled"]) === false}
                    />
                    <RedLineChip
                      label="production_activated"
                      ok={asBool(runReport["production_activated"]) === false}
                    />
                    <RedLineChip
                      label="real_signoff_count"
                      ok={Number(runReport["real_signoff_count"] ?? 0) === 0}
                    />
                  </div>
                ) : null}
                <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-white p-3 text-xs text-slate-600">
                  {JSON.stringify(runReport, null, 2)}
                </pre>
              </div>
            ) : null}
          </section>

          {/* 按 id 读取报告 */}
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-800">按 simulation_id 读取历史报告</h2>
            <div className="mt-3 flex items-center gap-2">
              <input
                value={reportIdInput}
                onChange={(e) => setReportIdInput(e.target.value)}
                placeholder="粘贴 simulation_id（进程内缓存，重启清空）"
                className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700"
              />
              <button
                onClick={() => void fetchReportById()}
                disabled={!reportIdInput.trim()}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 disabled:opacity-50"
              >
                读取
              </button>
            </div>
            {reportByIdError ? (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
                ⚠️ {reportByIdError}
              </div>
            ) : null}
            {reportById ? (
              <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-600">
                {JSON.stringify(reportById, null, 2)}
              </pre>
            ) : null}
          </section>

          {/* 底部再次声明 */}
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-5 py-4">
            <p className="text-sm font-semibold text-amber-800">声明</p>
            <p className="mt-1 text-xs text-amber-700">
              以上所有结果均为 SIMULATION_ONLY，与真实生产证据无关。真实生产激活仍须由主理人在人类终端、
              四角色签署后显式执行（engineering_enabled 当前恒为 false）。
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
          等待身份校验…（若长时间停留，请确认已以具备 governance:release:read 的真实责任人身份登录。）
        </div>
      )}
    </main>
  );
}
