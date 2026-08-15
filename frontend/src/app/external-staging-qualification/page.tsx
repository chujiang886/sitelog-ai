"use client";

/**
 * Phase 3.9.10 外部预生产环境资格验证 Dashboard（Task 27）。
 *
 * 只读展示：8 资源 / 配置-验证 / 连接性 / 隔离 / 部署目标 / 运行时健康 /
 * 遥测 / 告警 / TLS / 证据 / pending / 闸门。
 *
 * 红线（fail-closed，与后端同源）：
 * - 页面顶部强制显示「EXTERNAL STAGING — NOT PRODUCTION」；
 * - **禁止**任何 Production GO / Deploy / Rollback 按钮；
 * - 所有数据来自只读 API，本页不持有状态、不写密钥、不部署；
 * - 当前真实外部资源未提供 → 全部 pending，页面如实展示，不伪装验证。
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface ResourceSummary {
  total: number;
  configured: number;
  verified: number;
  pending: number;
  resource_ids: string[];
}

interface StatusResp {
  gate_status: string;
  environment: string;
  production: boolean;
  external_pending: number;
  engineering_enabled: boolean;
  production_activation_prohibited: boolean;
}

interface IsolationSummary {
  total: number;
  verified: number;
  pending: number;
  blocked: number;
}

interface RuntimeSummary {
  total: number;
  healthy: number;
  unknown: number;
  not_configured: number;
  unknown_treated_as_healthy: boolean;
}

interface GateCheck {
  name: string;
  passed: boolean;
  severity: string;
  detail: string;
}

interface PackageResp {
  gate: { status: string };
  resource_registry_summary: ResourceSummary;
  isolation_summary: IsolationSummary;
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

export default function ExternalStagingQualificationPage(): JSX.Element {
  const status = useGet<StatusResp>("/external-staging/qualification/status");
  const resources = useGet<{ registry_summary: ResourceSummary }>(
    "/external-staging/qualification/resources"
  );
  const isolation = useGet<IsolationSummary>("/external-staging/qualification/isolation");
  const runtime = useGet<RuntimeSummary>("/external-staging/qualification/runtime-health");
  const gate = useGet<{ gate_status: string; gate_checks: GateCheck[] }>(
    "/external-staging/qualification/gate"
  );
  const pkg = useGet<PackageResp>("/external-staging/qualification/package");

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p className="text-sm font-bold uppercase tracking-wide text-amber-800">
          EXTERNAL STAGING — NOT PRODUCTION
        </p>
        <p className="mt-1 text-xs text-amber-700">
          外部预生产环境资格验证层。本页面仅展示只读资格状态；不提供任何 Production
          GO / Deploy / Rollback 按钮，不写密钥、不部署。
        </p>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          外部预生产环境资格验证（Phase 3.9.10）
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          真实外部资源未提供 → 全部 pending（fail-closed 不伪造验证）。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card title="闸门状态" value={gate.data?.gate_status ?? "loading"} />
        <Card
          title="外部资源 Pending"
          value={String(status.data?.external_pending ?? "-")}
        />
        <Card
          title="隔离待证"
          value={String(isolation.data?.pending ?? "-")}
        />
        <Card
          title="运行时未接入"
          value={String(runtime.data?.not_configured ?? "-")}
        />
      </div>

      <Panel title="8 资源登记">
        {resources.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {resources.data.registry_summary.resource_ids.map((rid) => (
              <li key={rid} className="flex items-center justify-between">
                <span>{rid}</span>
                <Badge ok={false} label="PENDING" />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="跨环境隔离（9 项）">
        {isolation.data ? (
          <div className="flex gap-3 text-sm">
            <Badge ok={false} label={`待证 ${isolation.data.pending}`} />
            <Badge ok={isolation.data.verified > 0} label={`已证 ${isolation.data.verified}`} />
            <Badge ok={isolation.data.blocked === 0} label={`拦截 ${isolation.data.blocked}`} />
          </div>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="运行时健康（13 组件）">
        {runtime.data ? (
          <div className="flex gap-3 text-sm">
            <Badge ok={false} label={`NOT_CONFIGURED ${runtime.data.not_configured}`} />
            <Badge ok={runtime.data.unknown_treated_as_healthy === false} label="UNKNOWN≠HEALTHY" />
          </div>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="资格闸门检查">
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
        <Panel title="机器可读资格包">
          <div className="space-y-1 text-xs text-slate-600">
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
