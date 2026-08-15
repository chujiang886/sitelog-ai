"use client";

/**
 * Phase 3.9.12 外部预生产供给算子就绪 Dashboard（Task 28）。
 *
 * 只读展示：供给就绪状态 / 8 资源 BOM / Operator Gate（独立 3 态）/ IaC 干跑校验 /
 * 供给算子包 / Runbook 引用。
 *
 * 红线（fail-closed，与后端同源）：
 * - 页面顶部强制显示「EXTERNAL STAGING — NOT PRODUCTION」；
 * - **禁止**任何 Provision / Apply / Deploy / Rollback 按钮；
 * - 所有数据来自只读 API，本页不持有状态、不写密钥、不部署；
 * - 当前真实外部资源未提供 → 全部 pending，页面如实展示，不伪装供给验证。
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface StatusResp {
  phase: string;
  terminal_state: string;
  operator_gate_status: string;
  environment: string;
  production: boolean;
  pending_resources: number;
  engineering_enabled: boolean;
  production_activation_prohibited: boolean;
  contains_real_secret: boolean;
}

interface BomResource {
  resource_id: string;
  resource_type: string;
  required: boolean;
  owner_role: string;
  default_provider_service: string;
  iac_module: string;
  status: string;
}

interface BomResp {
  environment: string;
  production: boolean;
  total: number;
  pending: number;
  resources: BomResource[];
}

interface GateCheck {
  name: string;
  passed: boolean;
  severity: string;
  detail: string;
}

interface GateResp {
  operator_gate_status: string;
  gate_checks: GateCheck[];
}

interface IacDryRunResp {
  iac_dir: string;
  scanned_files: string[];
  credential_leak_hits: string[];
  count_zero_modules: string[];
  default_provider: string;
  provider_ok: boolean;
  all_ok: boolean;
}

interface PackageResp {
  phase: string;
  gate: { status: string };
  terminal_state: string;
  contains_real_secret: boolean;
  production_activation_prohibited: boolean;
  engineering_enabled: boolean;
  package_hash: string;
}

interface RunbookResp {
  provisioning_runbook: string;
  cleanup_rollback_runbook: string;
  human_input_table: string;
  operator_gate_doc: string;
  capacity_baseline: string;
  execution_mode: string[];
  forbidden_execution_mode: string[];
  operator_gate_states: string[];
  engineering_enabled: boolean;
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

function Card({ title, value }: { title: string; value: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{title}</p>
      <p className="mt-1 text-lg font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="mb-2 text-sm font-medium text-slate-700">{title}</p>
      {children}
    </div>
  );
}

export default function ExternalStagingProvisioningPage(): JSX.Element {
  const status = useGet<StatusResp>("/api/external-staging-provisioning/status");
  const bom = useGet<BomResp>("/api/external-staging-provisioning/bom");
  const gate = useGet<GateResp>("/api/external-staging-provisioning/gate");
  const iac = useGet<IacDryRunResp>("/api/external-staging-provisioning/iac-dry-run");
  const pkg = useGet<PackageResp>("/api/external-staging-provisioning/package");
  const runbook = useGet<RunbookResp>("/api/external-staging-provisioning/runbook");

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p className="text-sm font-bold uppercase tracking-wide text-amber-800">
          EXTERNAL STAGING — NOT PRODUCTION
        </p>
        <p className="mt-1 text-xs text-amber-700">
          外部预生产供给算子就绪层（Phase 3.9.12）。本页面仅展示只读供给就绪状态；
          不提供任何 Provision / Apply / Deploy / Rollback 按钮，不写密钥、不部署。
        </p>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          外部预生产供给算子就绪（Phase 3.9.12）
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          真实外部资源未提供 → 全部 pending（fail-closed 不伪造供给验证）。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card
          title="Operator Gate"
          value={gate.data?.operator_gate_status ?? "loading"}
        />
        <Card
          title="资源 Pending"
          value={String(status.data?.pending_resources ?? "-")}
        />
        <Card title="BOM 总数" value={String(bom.data?.total ?? "-")} />
        <Card
          title="IaC 干跑"
          value={iac.data ? (iac.data.all_ok ? "PASS" : "FAIL") : "loading"}
        />
      </div>

      <Panel title="8 资源供给 BOM（诚实 PENDING）">
        {bom.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {bom.data.resources.map((r, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>
                  {i + 1}. {r.resource_type} ({r.owner_role})
                </span>
                <Badge ok={false} label={r.status.toUpperCase()} />
              </li>
            ))}
            <li className="pt-1 text-xs text-slate-400">
              pending = {bom.data.pending} / {bom.data.total}
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="Operator Gate 检查项（独立 3 态）">
        {gate.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {gate.data.gate_checks.map((c, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>{c.name}</span>
                <Badge ok={c.passed} label={c.passed ? "PASS" : "FAIL"} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="IaC 干跑校验（fail-closed）">
        {iac.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>默认 provider：{iac.data.default_provider}</li>
            <li>count=0 占位模块数：{iac.data.count_zero_modules.length} / 4</li>
            <li>凭据泄漏命中：{iac.data.credential_leak_hits.length}</li>
            <li>
              <Badge ok={iac.data.all_ok} label={iac.data.all_ok ? "ALL_OK" : "FAIL"} />
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="Runbook 与人工输入">
        {runbook.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>供给 Runbook：{runbook.data.provisioning_runbook}</li>
            <li>清理/回滚 Runbook：{runbook.data.cleanup_rollback_runbook}</li>
            <li>人工输入表：{runbook.data.human_input_table}</li>
            <li>容量基线：{runbook.data.capacity_baseline}</li>
            <li>执行模式：{runbook.data.execution_mode.join(" / ")}</li>
            <li>禁止模式：{runbook.data.forbidden_execution_mode.join(" / ")}</li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="机器可读供给算子包">
        {pkg.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>phase：{pkg.data.phase}</li>
            <li>terminal_state：{pkg.data.terminal_state}</li>
            <li>contains_real_secret：{String(pkg.data.contains_real_secret)}</li>
            <li>engineering_enabled：{String(pkg.data.engineering_enabled)}</li>
            <li className="break-all text-xs text-slate-400">
              package_hash：{pkg.data.package_hash}
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>
    </div>
  );
}
