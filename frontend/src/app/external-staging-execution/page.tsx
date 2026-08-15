"use client";

/**
 * Phase 3.9.11 外部预生产执行与资格验证 Dashboard（Task 35）。
 *
 * 只读展示：执行计划（10 步）/ 8 资源适配器探针 / 13 证据链 / 执行闸门 /
 * 安全校验（allowed/forbidden actions）/ 机器可读执行包。
 *
 * 红线（fail-closed，与后端同源）：
 * - 页面顶部强制显示「EXTERNAL STAGING — NOT PRODUCTION」；
 * - **禁止**任何 Production GO / Deploy / Rollback 按钮；
 * - 所有数据来自只读 API，本页不持有状态、不写密钥、不部署；
 * - 当前真实外部资源未提供 → 全部 pending，页面如实展示，不伪装执行验证。
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface StatusResp {
  phase: string;
  terminal_state: string;
  gate_status: string;
  environment: string;
  production: boolean;
  external_pending: number;
  engineering_enabled: boolean;
  production_activation_prohibited: boolean;
  contains_real_secret: boolean;
}

interface PlanStep {
  kind: string;
  status: string;
  is_real_execution: boolean;
}

interface PlanResp {
  any_real_execution: boolean;
  step_count: number;
  steps: PlanStep[];
  production_activation_prohibited: boolean;
}

interface GateCheck {
  name: string;
  passed: boolean;
  severity: string;
  detail: string;
}

interface EvidenceResp {
  count: number;
  none_contains_secret: boolean;
  all_scope_external_staging: boolean;
  chain_hash: string;
}

interface ResourceRow {
  resource_id: string;
  resource_type: string;
  configured: boolean;
  verified: boolean;
  qualification_status: string;
  probe_status: string;
}

interface ResourcesResp {
  total: number;
  resources: ResourceRow[];
}

interface PackageResp {
  gate: { status: string };
  terminal_state: string;
  contains_real_secret: boolean;
  production_activation_prohibited: boolean;
  engineering_enabled: boolean;
  package_hash: string;
}

function useGet<T>(path: string): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API_BASE}${path}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setData(d as T);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [path]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading };
}

function Badge({ ok, label }: { ok: boolean; label: string }): JSX.Element {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
        ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
      }`}
    >
      {label}
    </span>
  );
}

export default function ExternalStagingExecutionPage(): JSX.Element {
  const status = useGet<StatusResp>("/api/external-staging-execution/status");
  const plan = useGet<PlanResp>("/api/external-staging-execution/plan");
  const gate = useGet<{ gate_status: string; gate_checks: GateCheck[] }>(
    "/api/external-staging-execution/gate"
  );
  const evidence = useGet<EvidenceResp>("/api/external-staging-execution/evidence");
  const resources = useGet<ResourcesResp>("/api/external-staging-execution/resources");
  const pkg = useGet<PackageResp>("/api/external-staging-execution/package");

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p className="text-sm font-bold uppercase tracking-wide text-amber-800">
          EXTERNAL STAGING — NOT PRODUCTION
        </p>
        <p className="mt-1 text-xs text-amber-700">
          外部预生产执行与资格验证层（Phase 3.9.11）。本页面仅展示只读执行状态；
          不提供任何 Production GO / Deploy / Rollback 按钮，不写密钥、不部署。
        </p>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          外部预生产执行与资格验证（Phase 3.9.11）
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          真实外部资源未提供 → 全部 pending（fail-closed 不伪造执行验证）。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card title="闸门状态" value={gate.data?.gate_status ?? "loading"} />
        <Card
          title="外部资源 Pending"
          value={String(status.data?.external_pending ?? "-")}
        />
        <Card
          title="执行计划步数"
          value={String(plan.data?.step_count ?? "-")}
        />
        <Card
          title="证据链条数"
          value={String(evidence.data?.count ?? "-")}
        />
      </div>

      <Panel title="执行计划（10 步 · 全 plan-only / contract-test / pending）">
        {plan.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {plan.data.steps.map((s, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>
                  {i + 1}. {s.kind}
                </span>
                <Badge ok={false} label={s.status.toUpperCase()} />
              </li>
            ))}
            <li className="pt-1 text-xs text-slate-400">
              any_real_execution = {String(plan.data.any_real_execution)}
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="8 资源适配器探针（诚实 PENDING）">
        {resources.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {resources.data.resources.map((r) => (
              <li key={r.resource_id} className="flex items-center justify-between">
                <span>
                  {r.resource_id} <span className="text-slate-400">({r.resource_type})</span>
                </span>
                <Badge ok={false} label={r.probe_status.toUpperCase()} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="执行闸门检查">
        {gate.data ? (
          <ul className="space-y-1 text-sm">
            {gate.data.gate_checks.map((c) => (
              <li key={c.name} className="flex items-center justify-between">
                <span>{c.name}</span>
                <Badge ok={c.passed} label={c.passed ? "PASS" : c.severity.toUpperCase()} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      {pkg.data ? (
        <Panel title="机器可读执行包">
          <div className="space-y-1 text-xs text-slate-600">
            <p>terminal_state = {pkg.data.terminal_state}</p>
            <p>contains_real_secret = {String(pkg.data.contains_real_secret)}</p>
            <p>production_activation_prohibited = {String(pkg.data.production_activation_prohibited)}</p>
            <p>engineering_enabled = {String(pkg.data.engineering_enabled)}</p>
            <p className="break-all">package_hash = {pkg.data.package_hash}</p>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function Card({ title, value }: { title: string; value: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs text-slate-400">{title}</p>
      <p className="mt-1 text-lg font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="mb-2 text-sm font-medium text-slate-700">{title}</p>
      {children}
    </div>
  );
}
