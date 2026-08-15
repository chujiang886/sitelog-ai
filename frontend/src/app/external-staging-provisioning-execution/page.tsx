"use client";

/**
 * Phase 3.9.13 外部预生产供给执行 Dashboard（T40-contract, T49-T53）。
 *
 * 只读展示：执行状态 / 8 资源状态机 / IaC 就绪 / 双钥匙 Apply Gate / 无伪造证据。
 *
 * 红线（fail-closed，与后端同源）：
 * - 页面顶部强制显示「EXTERNAL STAGING PROVISIONING EXECUTION — NOT PRODUCTION」；
 * - **禁止**任何 Apply / Provision / Deploy / Rollback 按钮；
 * - 所有数据来自只读 API，本页不持有状态、不写密钥、不部署；
 * - 当前真实外部资源未提供 → 全部 pending（0/8），页面如实展示，不伪装供给验证。
 */

import { useCallback, useEffect, useState } from "react";

const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const PREFIX = "/api/v1/external-staging-provisioning-execution";

interface StatusResp {
  phase: string;
  terminal_state: string;
  engineering_enabled: boolean;
  real_execution_allowed: boolean;
  total_resources: number;
  provisioned: number;
  registered: number;
  connected: number;
  isolated: number;
  qualified: number;
  any_real_progress: boolean;
  apply_gate_status: string;
  dual_key_authorized: boolean;
  fabrication_free: boolean;
  contains_real_secret: boolean;
  note: string;
}

interface ResourceState {
  resource_id: string;
  resource_type: string;
  state: string;
  is_failure: boolean;
  last_event: string;
  notes: string[];
}

interface ResourcesResp {
  engineering_enabled: boolean;
  real_execution_allowed: boolean;
  total: number;
  all_pending: boolean;
  resources: ResourceState[];
  contains_real_secret: boolean;
}

interface IacModule {
  module: string;
  path: string;
  found: boolean;
  classification: string;
  detail: string;
}

interface IacReadinessResp {
  modules: IacModule[];
  blocking_count: number;
  skeleton_audit_passed: boolean;
  verdict: string;
  real_execution_allowed: boolean;
  note: string;
}

interface ApplyGateResp {
  engineering_enabled: boolean;
  apply_gate_status: string;
  apply_gate_is_go: boolean;
  dual_key_authorized: boolean;
  real_execution_allowed: boolean;
  contains_real_secret: boolean;
}

interface EvidenceDetail {
  records: { resource_id: string; state: string; real_resource_provisioned: boolean; note: string }[];
  pending_human_items: string[];
  fabrication_free: boolean;
  evidence_hash: string;
}

interface ContractEndpoint {
  path: string;
  method: string;
  mutates: boolean;
}

interface EvidenceResp {
  engineering_enabled: boolean;
  fabrication_free: boolean;
  machine_package_hash: string;
  evidence: EvidenceDetail;
  contract: {
    version: string;
    base_path: string;
    real_execution_allowed: boolean;
    endpoints: ContractEndpoint[];
    forbidden: string[];
  };
  real_execution_allowed: boolean;
  contains_real_secret: boolean;
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

export default function ExternalStagingProvisioningExecutionPage(): JSX.Element {
  const status = useGet<StatusResp>(`${PREFIX}/status`);
  const resources = useGet<ResourcesResp>(`${PREFIX}/resources`);
  const iac = useGet<IacReadinessResp>(`${PREFIX}/iac-readiness`);
  const gate = useGet<ApplyGateResp>(`${PREFIX}/apply-gate`);
  const evidence = useGet<EvidenceResp>(`${PREFIX}/evidence`);

  const provisioned = status.data?.provisioned ?? 0;
  const total = status.data?.total_resources ?? 8;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p className="text-sm font-bold uppercase tracking-wide text-amber-800">
          EXTERNAL STAGING PROVISIONING EXECUTION — NOT PRODUCTION
        </p>
        <p className="mt-1 text-xs text-amber-700">
          外部预生产供给执行层（Phase 3.9.13）。本页面仅展示只读执行状态；
          不提供任何 Apply / Provision / Deploy / Rollback 按钮，不写密钥、不部署。
        </p>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          外部预生产供给执行（Phase 3.9.13）
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          真实外部资源未提供 → 全部 pending（0/8，fail-closed 不伪造供给验证）。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card title="已供给" value={`${provisioned} / ${total}`} />
        <Card
          title="Apply Gate"
          value={gate.data?.apply_gate_status ?? "loading"}
        />
        <Card
          title="双钥匙授权"
          value={gate.data ? (gate.data.dual_key_authorized ? "YES" : "PENDING") : "loading"}
        />
        <Card
          title="IaC 就绪"
          value={iac.data ? (iac.data.skeleton_audit_passed ? "PASS" : "BLOCKED") : "loading"}
        />
      </div>

      <Panel title="分项进度（不掩盖缺口）">
        {status.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>供给 provisioned：{status.data.provisioned} / {status.data.total_resources}</li>
            <li>注册 registered：{status.data.registered} / {status.data.total_resources}</li>
            <li>连通 connectivity：{status.data.connected} / {status.data.total_resources}</li>
            <li>隔离 isolation：{status.data.isolated} / {status.data.total_resources}</li>
            <li>合格 qualified：{status.data.qualified} / {status.data.total_resources}</li>
            <li>any_real_progress：{String(status.data.any_real_progress)}</li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="8 资源状态机（诚实 PENDING）">
        {resources.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {resources.data.resources.map((r, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>
                  {i + 1}. {r.resource_type} ({r.resource_id})
                </span>
                <Badge ok={false} label={r.state.toUpperCase()} />
              </li>
            ))}
            <li className="pt-1 text-xs text-slate-400">
              all_pending = {String(resources.data.all_pending)}
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="IaC 可执行就绪审计（fail-closed）">
        {iac.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            {iac.data.modules.map((m, i) => (
              <li key={i} className="flex items-center justify-between">
                <span>{m.module}</span>
                <Badge ok={m.classification !== "missing" && m.classification !== "incomplete"} label={m.classification.toUpperCase()} />
              </li>
            ))}
            <li className="pt-1 text-xs text-slate-400">
              verdict = {iac.data.verdict}；blocking = {iac.data.blocking_count}；
              real_execution_allowed = {String(iac.data.real_execution_allowed)}
            </li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="双钥匙 Apply Gate（永不 GO）">
        {gate.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>apply_gate_status：{gate.data.apply_gate_status}</li>
            <li>apply_gate_is_go：{String(gate.data.apply_gate_is_go)}</li>
            <li>dual_key_authorized：{String(gate.data.dual_key_authorized)}</li>
            <li>real_execution_allowed：{String(gate.data.real_execution_allowed)}</li>
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>

      <Panel title="无伪造证据链">
        {evidence.data ? (
          <ul className="space-y-1 text-sm text-slate-700">
            <li>fabrication_free：{String(evidence.data.fabrication_free)}</li>
            <li>engineering_enabled：{String(evidence.data.engineering_enabled)}</li>
            <li>contains_real_secret：{String(evidence.data.contains_real_secret)}</li>
            <li className="break-all text-xs text-slate-400">
              machine_package_hash：{evidence.data.machine_package_hash}
            </li>
            <li className="break-all text-xs text-slate-400">
              evidence_hash：{evidence.data.evidence.evidence_hash}
            </li>
            <li className="pt-1 text-xs text-slate-400">待真人动作：</li>
            {evidence.data.evidence.pending_human_items.map((it, i) => (
              <li key={i} className="text-xs text-amber-700">· {it}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-400">加载中…</p>
        )}
      </Panel>
    </div>
  );
}
