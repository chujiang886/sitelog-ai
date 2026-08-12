"use client";

/**
 * Phase 3.9.2 T10 —— 企业生产发布闸门控制台（只读 + 真实人工签署）。
 *
 * 设计红线（与后端同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；请求头由 IdentityProvider 产出，
 *   而 IdentityProvider 只会为通过 assertHumanIdentity 的人类主体产出头（红线⑥）。
 * - **无自动上线按钮**：本页面不存在任何"一键部署 / 一键激活 / 自动 GO"入口。
 * - **无 AI 批准按钮**：AI 只生成闸门口只读快照与 Go/No-Go 草稿，最终 GO 只能由
 *   真实责任人（production-owner / release-manager / security-owner / auditor）线下
 *   通过签署端点落 AuditService 产生（红线②/⑧/⑩）。
 * - 人工只能签署**自己**的 GO / NO-GO / NEED_MORE_EVIDENCE，且必须填理由（留痕审计）。
 * - 取不到合法身份时页面**不降级**：直接显示错误并禁用一切签署动作。
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

const RELEASE_ID = "RC-3.9.2";

/** 13 项闸门检查键（与后端 ProductionReleaseGate.CHECK_KEYS 对齐）。 */
const GATE_CHECK_KEYS: readonly string[] = [
  "git_workspace_integrity",
  "commit_sha_exists",
  "full_test_results_green",
  "production_security_scanner",
  "identity_security_scanner",
  "governance_quality_gate",
  "staging_validation",
  "rollback_drill",
  "recovery_validation",
  "database_migration_status",
  "configuration_baseline",
  "deployment_documentation",
  "evidence_completeness",
];

type SignoffRole = "production-owner" | "release-manager" | "security-owner" | "auditor";
type SignoffDecision = "go" | "no_go" | "need_more_evidence";

const ROLE_LABEL: Record<SignoffRole, string> = {
  "production-owner": "生产负责人",
  "release-manager": "发布经理",
  "security-owner": "安全负责人",
  auditor: "审计员",
};

const DECISION_LABEL: Record<SignoffDecision, string> = {
  go: "GO（放行）",
  no_go: "NO-GO（不放行）",
  need_more_evidence: "需补充证据",
};

interface EvidenceItem {
  evidence_id: string;
  evidence_type?: string;
  source?: string;
  verification_status?: string;
  integrity_status?: string;
  source_reference?: string;
  detail?: string;
}

interface ReleaseSnapshot {
  release_id: string;
  version: string;
  commit_sha: string;
  branch: string;
  status: string;
  release_approved: boolean;
  engineering_enabled: boolean;
  gate_status: string;
  evidence_summary: EvidenceItem[];
}

interface GateResult {
  status: string;
  checks: Record<string, boolean>;
  missing: string[];
  note?: string;
}

interface Manifest {
  release_version: string;
  commit_sha: string;
  artifact_hashes: Record<string, string>;
  migration_revision?: string | null;
  config_baseline?: string | null;
  security_scan_ref?: string | null;
  test_report_ref?: string | null;
  rollback_version?: string | null;
  documentation_version?: string | null;
}

interface RollbackReference {
  last_known_good_version: string;
  last_known_good_commit: string;
  database_revision?: string | null;
  config_baseline?: string | null;
  rollback_steps_reference?: string | null;
  recovery_validation_reference?: string | null;
  verified: boolean;
}

function gateStatusTone(status: string): string {
  switch (status) {
    case "ready_for_human_review":
      return "bg-amber-100 text-amber-700";
    case "blocked":
      return "bg-red-100 text-red-700";
    case "pending_verification":
      return "bg-blue-100 text-blue-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function gateStatusLabel(status: string): string {
  switch (status) {
    case "ready_for_human_review":
      return "待人工复核";
    case "blocked":
      return "阻断";
    case "pending_verification":
      return "待核验";
    default:
      return status;
  }
}

export default function GovernanceReleasePage(): JSX.Element {
  const [snapshot, setSnapshot] = useState<ReleaseSnapshot | null>(null);
  const [gate, setGate] = useState<GateResult | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [rollback, setRollback] = useState<RollbackReference | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);

  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);

  const [signRole, setSignRole] = useState<SignoffRole>("release-manager");
  const [signDecision, setSignDecision] = useState<SignoffDecision>("need_more_evidence");
  const [signReason, setSignReason] = useState<string>("");
  const [signResult, setSignResult] = useState<string>("");

  const load = useCallback(async (): Promise<void> => {
    setError("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      requirePermission(me, "governance:release:read");
      setIdentity(me);

      const headers = await provider.getAuthHeaders();
      const [snapRes, gateRes, manifestRes, rollbackRes, evRes] = await Promise.all([
        fetch(`${API_BASE}/governance/releases?release_id=${encodeURIComponent(RELEASE_ID)}`, { headers }),
        fetch(`${API_BASE}/governance/releases/${encodeURIComponent(RELEASE_ID)}/gate`, { headers }),
        fetch(`${API_BASE}/governance/releases/${encodeURIComponent(RELEASE_ID)}/manifest`, { headers }),
        fetch(`${API_BASE}/governance/releases/${encodeURIComponent(RELEASE_ID)}`, { headers }),
        fetch(`${API_BASE}/governance/releases/${encodeURIComponent(RELEASE_ID)}/evidence`, { headers }),
      ]);
      if (!snapRes.ok) throw new Error(`加载发布候选失败（${snapRes.status}）`);
      if (!gateRes.ok) throw new Error(`加载闸门失败（${gateRes.status}）`);
      if (!manifestRes.ok) throw new Error(`加载清单失败（${manifestRes.status}）`);
      if (!rollbackRes.ok) throw new Error(`加载回滚引用失败（${rollbackRes.status}）`);
      if (!evRes.ok) throw new Error(`加载证据链失败（${evRes.status}）`);

      setSnapshot((await snapRes.json()) as ReleaseSnapshot);
      setGate((await gateRes.json()) as GateResult);
      setManifest((await manifestRes.json()) as Manifest);
      const full = (await rollbackRes.json()) as { rollback_reference?: RollbackReference };
      setRollback(full.rollback_reference ?? null);
      setEvidence((await evRes.json()) as EvidenceItem[]);
    } catch (e) {
      setIdentity(null);
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submitSignoff = async (): Promise<void> => {
    setBusy(true);
    setError("");
    setSignResult("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      // 签署前二次校验权限（红线⑥：只有真人且持有 RELEASE_SIGNOFF 才能签署）。
      requirePermission(me, "governance:release:signoff");
      const headers = await provider.getAuthHeaders();

      const reason = signReason.trim();
      if (!reason) {
        throw new Error("签署必须填写理由（留痕审计）");
      }
      const res = await fetch(
        `${API_BASE}/governance/releases/${encodeURIComponent(RELEASE_ID)}/signoff`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({
            role: signRole,
            decision: signDecision,
            reason,
            evidence_snapshot: {
              gate_status: gate?.status,
              snapshot_release_approved: snapshot?.release_approved,
            },
          }),
        }
      );
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`签署失败（${res.status}）${detail ? `：${detail}` : ""}`);
      }
      const body = (await res.json()) as { signoff_id?: string };
      setSignResult(`签署已记录（${body.signoff_id ?? "ok"}）。注意：本操作仅留痕，不构成生产放行。`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "签署失败");
    } finally {
      setBusy(false);
    }
  };

  const canSign =
    identity !== null && hasPermission(identity, "governance:release:signoff");

  return (
    <section className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-sm font-medium text-boip-primary-main">生产发布闸门 · 责任人专属</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">生产发布闸门控制台</h1>
      <p className="mt-2 text-sm text-slate-500">
        只读查看发布候选、证据链、闸门、清单与回滚引用。本页面不部署、不激活、不自动放行；
        最终 GO 只能由真实责任人线下签署。
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
          未取得责任人身份，签署动作已全部禁用。
        </p>
      )}

      {error ? (
        <p className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {signResult ? (
        <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {signResult}
        </p>
      ) : null}

      {/* 发布候选概览 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">发布候选</h2>
      {snapshot ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">Release ID</p>
            <p className="mt-1 font-mono text-sm text-slate-800">{snapshot.release_id}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">版本</p>
            <p className="mt-1 text-sm text-slate-800">{snapshot.version}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">分支</p>
            <p className="mt-1 font-mono text-sm text-slate-800">{snapshot.branch}</p>
          </div>
          <div className="col-span-2 rounded-lg border border-slate-200 bg-white p-4 sm:col-span-3">
            <p className="text-xs uppercase tracking-wide text-slate-400">Commit SHA</p>
            <p className="mt-1 break-all font-mono text-sm text-slate-800">{snapshot.commit_sha}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">候选状态</p>
            <p className="mt-1 text-sm text-slate-800">{snapshot.status}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">闸门状态</p>
            <span
              className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-medium ${gateStatusTone(
                snapshot.gate_status
              )}`}
            >
              {gateStatusLabel(snapshot.gate_status)}
            </span>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">engineering_enabled</p>
            <p
              className={`mt-1 text-sm font-semibold ${
                snapshot.engineering_enabled ? "text-red-600" : "text-emerald-600"
              }`}
            >
              {String(snapshot.engineering_enabled)}
            </p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 13 项闸门检查 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">发布闸门检查（13 项）</h2>
      {gate ? (
        <>
          <p className="mt-2 text-sm text-slate-500">
            闸门状态：
            <span className="font-medium text-slate-700">{gateStatusLabel(gate.status)}</span>
            {gate.missing.length > 0 ? ` · 缺失 ${gate.missing.length} 项` : ""}
          </p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {GATE_CHECK_KEYS.map((key) => {
              const ok = gate.checks[key] === true;
              return (
                <div
                  key={key}
                  className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm"
                >
                  <span className="font-mono text-slate-700">{key}</span>
                  <span
                    className={`rounded-full px-3 py-0.5 text-xs font-medium ${
                      ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {ok ? "通过" : "待核验/缺失"}
                  </span>
                </div>
              );
            })}
          </div>
          {gate.missing.length > 0 ? (
            <p className="mt-3 text-sm text-red-600">
              缺失项：{gate.missing.join("、")}
            </p>
          ) : null}
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 清单 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">发布清单（SHA-256）</h2>
      {manifest ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-5">
          <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <p className="text-slate-600">版本：<span className="text-slate-800">{manifest.release_version}</span></p>
            <p className="text-slate-600">迁移修订：<span className="text-slate-800">{manifest.migration_revision ?? "—"}</span></p>
            <p className="text-slate-600">安全扫描引用：<span className="text-slate-800">{manifest.security_scan_ref ?? "—"}</span></p>
            <p className="text-slate-600">测试报告引用：<span className="text-slate-800">{manifest.test_report_ref ?? "—"}</span></p>
            <p className="text-slate-600">回滚版本：<span className="text-slate-800">{manifest.rollback_version ?? "—"}</span></p>
            <p className="text-slate-600">文档版本：<span className="text-slate-800">{manifest.documentation_version ?? "—"}</span></p>
          </div>
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">产物哈希</p>
            <ul className="mt-1 space-y-1">
              {Object.entries(manifest.artifact_hashes).map(([k, v]) => (
                <li key={k} className="break-all font-mono text-xs text-slate-600">
                  {k} → {v}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 回滚引用 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">回滚引用</h2>
      {rollback ? (
        <div className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <p className="text-slate-600">Last Known Good 版本：<span className="text-slate-800">{rollback.last_known_good_version}</span></p>
          <p className="text-slate-600">引用校验：<span className={rollback.verified ? "text-emerald-600" : "text-amber-600"}>{rollback.verified ? "完整" : "待核验"}</span></p>
          <p className="col-span-1 break-all font-mono text-slate-600">Commit：{rollback.last_known_good_commit}</p>
          <p className="text-slate-600">数据库修订：<span className="text-slate-800">{rollback.database_revision ?? "—"}</span></p>
          <p className="col-span-2 text-slate-600">回滚步骤：<span className="text-slate-800">{rollback.rollback_steps_reference ?? "—"}</span></p>
          <p className="col-span-2 text-slate-600">恢复校验：<span className="text-slate-800">{rollback.recovery_validation_reference ?? "—"}</span></p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 证据链 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">
        发布证据链（{evidence.length}）
      </h2>
      {evidence.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">暂无证据。</p>
      ) : (
        <div className="mt-3 space-y-3">
          {evidence.map((ev) => (
            <article
              key={ev.evidence_id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-mono text-sm font-semibold text-slate-900">
                  {ev.evidence_type ?? ev.evidence_id}
                </h3>
                <div className="flex gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      ev.verification_status === "verified"
                        ? "bg-emerald-100 text-emerald-700"
                        : ev.verification_status === "failed"
                        ? "bg-red-100 text-red-700"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {ev.verification_status ?? "未知"}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {ev.integrity_status ?? "—"}
                  </span>
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {ev.source_reference}
                {ev.detail ? ` · ${ev.detail}` : ""}
              </p>
            </article>
          ))}
        </div>
      )}

      {/* 真实人工签署区（唯一写入动作；无自动上线/AI 批准按钮） */}
      <h2 className="mt-10 text-xl font-semibold text-slate-800">真实人工签署</h2>
      <p className="mt-2 text-sm text-slate-500">
        签署仅记录到审计（append-only），<span className="font-medium text-slate-700">不构成生产放行</span>。
        最终 GO 须 production-owner / release-manager / security-owner / auditor 四方线下共同签署。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <label className="block text-xs font-medium text-slate-600">
          签署角色
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={signRole}
            onChange={(e) => setSignRole(e.target.value as SignoffRole)}
          >
            {(Object.keys(ROLE_LABEL) as SignoffRole[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block text-xs font-medium text-slate-600">
          签署决策
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={signDecision}
            onChange={(e) => setSignDecision(e.target.value as SignoffDecision)}
          >
            {(Object.keys(DECISION_LABEL) as SignoffDecision[]).map((d) => (
              <option key={d} value={d}>
                {DECISION_LABEL[d]}
              </option>
            ))}
          </select>
        </label>
        <textarea
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          rows={3}
          placeholder="请填写签署理由（必填，留痕审计）"
          value={signReason}
          onChange={(e) => setSignReason(e.target.value)}
        />
        <button
          type="button"
          disabled={busy || !canSign}
          title={
            canSign
              ? undefined
              : "当前责任人无「发布签署」权限（governance:release:signoff，仅 governance-admin 持有）"
          }
          onClick={() => void submitSignoff()}
          className="mt-2 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "提交中…" : "提交人工签署"}
        </button>
      </div>

      <p className="mt-8 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        提醒：本页面为「发布闸门与证据包」只读控制台。Phase 3.9.2 不执行真实部署、不开启
        engineering_enabled、不自动 GO。任何生产放行须主理人与专家线下提交真实证据并由真实责任人签署。
      </p>
    </section>
  );
}
