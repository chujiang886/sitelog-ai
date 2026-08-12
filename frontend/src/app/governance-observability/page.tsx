"use client";

/**
 * Phase 3.9.3 T18 —— 企业生产可观测性、SRE 与事故响应控制台（只读 + 真实人工事故动作）。
 *
 * 设计红线（与后端同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；请求头由 IdentityProvider 产出（红线⑨/⑩）。
 * - **无任何自动按钮**：本页面禁止出现 Auto Fix / Auto Rollback / Auto Resolve /
 *   Auto Close / AI Approve 入口（红线⑤/⑨）。
 * - 人工只能**手动**对自己正在响应的 Incident 执行 ACK / RESOLVE / CLOSE，且必须填
 *   incident_id 与理由（留痕审计）；这些动作只记录到 AuditService，绝不自动转移
 *   Incident 状态（红线⑨/⑩）。
 * - 所有监控视图均为准备层合成只读视图（simulation_only / pending_verification），
 *   不描述成真实生产观测（红线⑪）。
 * - 取不到合法身份时页面**不降级**：直接显示错误并禁用一切动作。
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

interface ComponentHealth {
  component: string;
  status: string;
  checked_at: string;
  source: string;
  latency_ms: number | null;
  error: string;
  trace_reference: string;
  simulation_only: boolean;
}

interface HealthView {
  overall: string;
  simulation_only: boolean;
  note: string;
  components: ComponentHealth[];
  expected_components: string[];
}

interface SLOItem {
  slo_id: string;
  name: string;
  component: string;
  kind: string;
  target: number;
  window: string;
  threshold_verified: boolean;
  status: string;
}

interface SLOView {
  simulation_only: boolean;
  threshold_verified: boolean;
  total: number;
  met: number;
  breached: number;
  pending_verification: number;
  items: SLOItem[];
}

interface MetricsView {
  simulation_only: boolean;
  note: string;
  snapshots: unknown[];
}

interface IncidentListView {
  organization_id: string;
  simulation_only: boolean;
  active_incidents: unknown[];
  note: string;
}

function healthTone(status: string): string {
  switch (status) {
    case "healthy":
      return "bg-emerald-100 text-emerald-700";
    case "degraded":
      return "bg-amber-100 text-amber-700";
    case "unhealthy":
      return "bg-red-100 text-red-700";
    default:
      return "bg-slate-100 text-slate-600"; // UNKNOWN
  }
}

function healthLabel(status: string): string {
  switch (status) {
    case "healthy":
      return "健康";
    case "degraded":
      return "降级";
    case "unhealthy":
      return "异常";
    default:
      return "未知（未观测）";
  }
}

export default function GovernanceObservabilityPage(): JSX.Element {
  const [health, setHealth] = useState<HealthView | null>(null);
  const [slo, setSlo] = useState<SLOView | null>(null);
  const [metrics, setMetrics] = useState<MetricsView | null>(null);
  const [incidents, setIncidents] = useState<IncidentListView | null>(null);

  const [error, setError] = useState<string>("");
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);

  // 人工事故动作面板
  const [incidentId, setIncidentId] = useState<string>("");
  const [actionReason, setActionReason] = useState<string>("");
  const [actionBusy, setActionBusy] = useState<boolean>(false);
  const [actionResult, setActionResult] = useState<string>("");

  const load = useCallback(async (): Promise<void> => {
    setError("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      requirePermission(me, "governance:observability:read");
      setIdentity(me);

      const headers = await provider.getAuthHeaders();
      const [hRes, sRes, mRes, iRes] = await Promise.all([
        fetch(`${API_BASE}/governance/observability/health`, { headers }),
        fetch(`${API_BASE}/governance/observability/slo`, { headers }),
        fetch(`${API_BASE}/governance/observability/metrics`, { headers }),
        fetch(`${API_BASE}/governance/incidents`, { headers }),
      ]);
      if (!hRes.ok) throw new Error(`加载健康视图失败（${hRes.status}）`);
      if (!sRes.ok) throw new Error(`加载 SLO 失败（${sRes.status}）`);
      if (!mRes.ok) throw new Error(`加载指标失败（${mRes.status}）`);
      if (!iRes.ok) throw new Error(`加载事故列表失败（${iRes.status}）`);

      setHealth((await hRes.json()) as HealthView);
      setSlo((await sRes.json()) as SLOView);
      setMetrics((await mRes.json()) as MetricsView);
      setIncidents((await iRes.json()) as IncidentListView);
    } catch (e) {
      setIdentity(null);
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submitIncidentAction = async (action: "acknowledge" | "resolve" | "close"): Promise<void> => {
    setActionBusy(true);
    setError("");
    setActionResult("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      // 动作前二次校验权限（红线⑨/⑩：只有真人且持有 INCIDENT_ACTION 才能执行）。
      requirePermission(me, "governance:incident:action");
      const headers = await provider.getAuthHeaders();

      const id = incidentId.trim();
      if (!id) {
        throw new Error("必须填写正在响应的 incident_id");
      }
      const reason = actionReason.trim();
      if (!reason) {
        throw new Error("动作必须填写理由（留痕审计）");
      }
      const res = await fetch(
        `${API_BASE}/governance/incidents/${encodeURIComponent(id)}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({ reason }),
        }
      );
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`动作 ${action} 失败（${res.status}）${detail ? `：${detail}` : ""}`);
      }
      const body = (await res.json()) as { recorded_at?: string };
      setActionResult(
        `${action} 已记录（${body.recorded_at ?? "ok"}）。注意：本操作仅留痕，不自动转移 Incident 状态。`
      );
      setActionReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "动作失败");
    } finally {
      setActionBusy(false);
    }
  };

  const canAct =
    identity !== null && hasPermission(identity, "governance:incident:action");

  return (
    <section className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-sm font-medium text-boip-primary-main">生产可观测性 · 责任人专属</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">生产健康与事故响应控制台</h1>
      <p className="mt-2 text-sm text-slate-500">
        只读查看组件健康、指标、SLO / 错误预算、活动告警与事故。本页面不自动修复、不自动回滚、
        不自动解决、不自动关闭、不 AI 批准；所有事故动作须真实责任人手动执行并留痕。
      </p>

      {identity ? (
        <p className="mt-3 text-xs text-slate-500">
          当前责任人：
          <span className="font-medium text-slate-700">
            {identity.displayName ?? identity.actorId}
          </span>
          （{identity.actorId}）· 身份来源 {identity.scheme}
          {identity.roles && identity.roles.length > 0
            ? ` · 角色 ${identity.roles.join("、")}`
            : " · 未分配角色"}
        </p>
      ) : (
        <p className="mt-3 text-xs text-slate-400">
          未取得责任人身份，事故动作已全部禁用。
        </p>
      )}

      {error ? (
        <p className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {actionResult ? (
        <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {actionResult}
        </p>
      ) : null}

      {/* 总览健康 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">总览健康</h2>
      {health ? (
        <div className="mt-3 flex items-center gap-3">
          <span
            className={`inline-block rounded-full px-4 py-1.5 text-sm font-medium ${healthTone(
              health.overall
            )}`}
          >
            {healthLabel(health.overall)}
          </span>
          {health.simulation_only ? (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">
              合成只读视图（simulation_only）
            </span>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 组件健康 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">组件健康（11 类）</h2>
      {health ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {health.components.map((c) => (
            <div
              key={c.component}
              className="rounded-lg border border-slate-200 bg-white px-4 py-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-slate-700">{c.component}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${healthTone(
                    c.status
                  )}`}
                >
                  {healthLabel(c.status)}
                </span>
              </div>
              {c.simulation_only ? (
                <p className="mt-1 text-[11px] text-slate-400">合成只读，待生产接入</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* SLO / 错误预算 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">SLO 与错误预算</h2>
      {slo ? (
        <>
          <p className="mt-2 text-sm text-slate-500">
            阈值验证：
            <span className="font-medium text-slate-700">
              {slo.threshold_verified ? "已验证" : "pending_verification（待人工设定真实业务目标）"}
            </span>
            {slo.pending_verification > 0 ? ` · 待核验 ${slo.pending_verification} 项` : ""}
          </p>
          <div className="mt-3 space-y-2">
            {slo.items.map((s) => (
              <div
                key={s.slo_id}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm"
              >
                <span className="text-slate-700">
                  {s.name}
                  <span className="ml-2 font-mono text-xs text-slate-400">
                    {s.kind} · 目标 {s.target}
                  </span>
                </span>
                <span
                  className={`rounded-full px-3 py-0.5 text-xs font-medium ${
                    s.status === "met"
                      ? "bg-emerald-100 text-emerald-700"
                      : s.status === "breached"
                      ? "bg-red-100 text-red-700"
                      : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 指标 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">指标</h2>
      {metrics ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
          {metrics.simulation_only ? "合成只读视图（simulation_only）：" : ""}
          {metrics.note}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 活动告警 / 事故 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">活动告警与事故</h2>
      {incidents ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">
            当前活动事故：
            <span className="font-medium text-slate-700">
              {incidents.active_incidents.length}
            </span>
            {incidents.simulation_only ? " · 准备层只读视图" : ""}
          </p>
          <p className="mt-1 text-xs text-slate-400">{incidents.note}</p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 真实人工事故动作（唯一写入动作；无 Auto Fix/Auto Rollback/Auto Resolve/Auto Close/AI Approve） */}
      <h2 className="mt-10 text-xl font-semibold text-slate-800">真实人工事故动作</h2>
      <p className="mt-2 text-sm text-slate-500">
        动作仅记录到审计（append-only），<span className="font-medium text-slate-700">
          不自动转移 Incident 状态</span>。须真实责任人手动填入正在响应的 incident_id 与理由。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <label className="block text-xs font-medium text-slate-600">
          incident_id（正在响应的事故）
          <input
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-mono"
            placeholder="INC-xxxx"
            value={incidentId}
            onChange={(e) => setIncidentId(e.target.value)}
          />
        </label>
        <textarea
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          rows={3}
          placeholder="请填写动作理由（必填，留痕审计）"
          value={actionReason}
          onChange={(e) => setActionReason(e.target.value)}
        />
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={actionBusy || !canAct}
            title={
              canAct
                ? undefined
                : "当前责任人无「事故动作」权限（governance:incident:action，仅 governance-admin 持有）"
            }
            onClick={() => void submitIncidentAction("acknowledge")}
            className="rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {actionBusy ? "提交中…" : "ACK 事故"}
          </button>
          <button
            type="button"
            disabled={actionBusy || !canAct}
            onClick={() => void submitIncidentAction("resolve")}
            className="rounded-md bg-slate-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            RESOLVE 事故
          </button>
          <button
            type="button"
            disabled={actionBusy || !canAct}
            onClick={() => void submitIncidentAction("close")}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            CLOSE 事故
          </button>
        </div>
      </div>

      <p className="mt-8 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        提醒：本页面为「生产可观测性与事故响应」只读控制台。Phase 3.9.3 不发送真实生产告警、
        不执行真实回滚 / 部署、不自动关闭 Incident、不开启 engineering_enabled。任何生产事故
        处置须由真实 SRE / production-owner / security-owner / incident-commander 线下执行。
      </p>
    </section>
  );
}
