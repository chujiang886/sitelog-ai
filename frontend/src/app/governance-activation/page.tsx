"use client";

/**
 * Phase 3.9.6 Task 18 —— 生产激活证据就绪控制台（只读 + 真实人工签署）。
 *
 * 设计红线（与后端同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；请求头由 IdentityProvider 产出，
 *   而 IdentityProvider 只会为通过 assertHumanIdentity 的人类主体产出头（红线⑥）。
 * - **无自动上线按钮**：本页面不存在任何"一键部署 / 一键激活 / 自动 GO"入口。
 * - **无 AI 批准按钮**：AI 只生成就绪态只读快照，最终 GO 只能由真实责任人
 *   （production-owner / release-manager / security-owner / auditor）线下通过签署端点落
 *   AuditService 产生（红线②/⑧/⑩）。
 * - 人工只能签署**自己**的 GO / NO-GO / NEED_MORE_EVIDENCE，且必须填理由与真实签署凭证（留痕审计）。
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

const RC_ID = "RC-3.9.6";

/** 8 项激活就绪检查键（与后端 ProductionActivationReadinessGate.CHECK_KEYS 对齐）。 */
const GATE_CHECK_KEYS: readonly string[] = [
  "engineering_enabled_false",
  "evidence_bundle_complete",
  "governance_integrity_9_9",
  "rollback_reference_present",
  "recovery_validation_present",
  "no_activation_blockers",
  "human_signoffs_complete",
  "no_pending_verification",
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

interface Blocker {
  blocker_id: string;
  category: string;
  description: string;
  source: string;
  evidence: string;
  owner_role: string;
  resolution_status: string;
}

interface PendingItem {
  id: string;
  phase: string;
  item: string;
  reason: string;
  required_evidence: string;
  required_role: string;
  current_status: string;
  source_report?: string;
}

interface SignoffReq {
  required_role: string;
  current_status: string;
  signed_by?: string | null;
  decision?: string | null;
  is_satisfied: boolean;
}

interface GateResult {
  status: string;
  checks: Record<string, boolean>;
  missing: string[];
  note?: string;
}

interface Contract {
  activation_allowed_for_human: boolean;
  required_gates: string[];
  required_evidence: string[];
  required_signoffs: string[];
  blocker_count: number;
  pending_count: number;
  note?: string;
}

interface Dossier {
  rc_id: string;
  engineering_enabled: boolean;
  evidence_bundle: { production_evidence_complete: boolean; [k: string]: unknown };
  signoff_requirements: SignoffReq[];
  sod: { ok: boolean; [k: string]: unknown };
  blockers: Blocker[];
  pending_verification: PendingItem[];
  readiness_gate: GateResult;
  contract: Contract;
  status_terminal: string;
}

function gateStatusTone(status: string): string {
  switch (status) {
    case "ready_for_human_signoff":
      return "bg-emerald-100 text-emerald-700";
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
    case "ready_for_human_signoff":
      return "待人工签署（可交真人裁决）";
    case "blocked":
      return "阻断";
    case "pending_verification":
      return "待核验";
    default:
      return status;
  }
}

export default function GovernanceActivationPage(): JSX.Element {
  const [dossier, setDossier] = useState<Dossier | null>(null);

  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);

  const [signRole, setSignRole] = useState<SignoffRole>("release-manager");
  const [signDecision, setSignDecision] = useState<SignoffDecision>("need_more_evidence");
  const [signReason, setSignReason] = useState<string>("");
  const [signRef, setSignRef] = useState<string>("");
  const [signResult, setSignResult] = useState<string>("");

  const load = useCallback(async (): Promise<void> => {
    setError("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      requirePermission(me, "governance:release:read");
      setIdentity(me);

      const headers = await provider.getAuthHeaders();
      const res = await fetch(
        `${API_BASE}/governance/activation/readiness?rc_id=${encodeURIComponent(RC_ID)}`,
        { headers }
      );
      if (!res.ok) throw new Error(`加载激活就绪 dossier 失败（${res.status}）`);
      setDossier((await res.json()) as Dossier);
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
      const ref = signRef.trim();
      if (!reason) throw new Error("签署必须填写理由（留痕审计）");
      if (!ref) throw new Error("签署必须携带真实 signature_reference（线下签署文档/工单/归档审批坐标）");

      const res = await fetch(
        `${API_BASE}/governance/activation/signoff?rc_id=${encodeURIComponent(RC_ID)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({
            role: signRole,
            decision: signDecision,
            reason,
            signature_reference: ref,
            evidence_scope_reviewed: [],
          }),
        }
      );
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`签署失败（${res.status}）${detail ? `：${detail}` : ""}`);
      }
      const body = (await res.json()) as { signoff_id?: string };
      setSignResult(`签署已记录（${body.signoff_id ?? "ok"}）。注意：本操作仅留痕，不构成生产放行。`);
      void load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "签署失败");
    } finally {
      setBusy(false);
    }
  };

  const canSign =
    identity !== null && hasPermission(identity, "governance:release:signoff");

  const gate = dossier?.readiness_gate ?? null;

  return (
    <section className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-sm font-medium text-boip-primary-main">生产激活证据就绪 · 责任人专属</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-900">生产激活证据就绪控制台</h1>

      {/* 终态横幅：BUILT_NO_GO / AWAITING_HUMAN */}
      <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-5 py-4">
        <p className="text-sm font-semibold text-amber-800">
          终态：{dossier?.status_terminal ?? "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO"}
        </p>
        <p className="mt-1 text-xs text-amber-700">
          全部软件证据 / 人类责任结构 / 检查包 / 回滚包 / 签署模板 / Go-No-Go 输入已备齐，
          但<span className="font-medium">未发生任何真实生产激活</span>。真实生产启用只能由主理人在人类终端、
          四角色线下签署后显式执行。
        </p>
      </div>

      <p className="mt-2 text-sm text-slate-500">
        只读查看激活就绪态、阻断器、待核验、四角色签署要求与工程激活契约。本页面不部署、不激活、
        不自动放行；最终 GO 只能由真实责任人线下签署。
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

      {/* 就绪概览 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">就绪概览</h2>
      {dossier ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">RC ID</p>
            <p className="mt-1 font-mono text-sm text-slate-800">{dossier.rc_id}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">就绪闸门</p>
            <span
              className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-medium ${gateStatusTone(
                dossier.readiness_gate.status
              )}`}
            >
              {gateStatusLabel(dossier.readiness_gate.status)}
            </span>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">engineering_enabled</p>
            <p
              className={`mt-1 text-sm font-semibold ${
                dossier.engineering_enabled ? "text-red-600" : "text-emerald-600"
              }`}
            >
              {String(dossier.engineering_enabled)}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">阻断器</p>
            <p className="mt-1 text-sm text-slate-800">{dossier.blockers.length} 项（未解决）</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">待核验</p>
            <p className="mt-1 text-sm text-slate-800">{dossier.pending_verification.length} 项</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">证据包完整</p>
            <p className="mt-1 text-sm text-slate-800">
              {String(dossier.evidence_bundle.production_evidence_complete)}
            </p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 8 项就绪检查 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">激活就绪检查（8 项）</h2>
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
            <p className="mt-3 text-sm text-red-600">缺失项：{gate.missing.join("、")}</p>
          ) : null}
        </>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 阻断器 B1-B6 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">
        生产激活阻断器（{dossier?.blockers.length ?? 0}）
      </h2>
      {dossier && dossier.blockers.length > 0 ? (
        <div className="mt-3 space-y-2">
          {dossier.blockers.map((b) => (
            <div key={b.blocker_id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <p className="font-mono text-sm font-semibold text-slate-900">{b.blocker_id}</p>
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                  {b.resolution_status}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-700">{b.description}</p>
              <p className="mt-1 text-xs text-slate-400">
                类别 {b.category} · 负责角色 {b.owner_role} · 来源 {b.source}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 待核验 PV1-PV6 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">
        待核验事项（{dossier?.pending_verification.length ?? 0}）
      </h2>
      {dossier && dossier.pending_verification.length > 0 ? (
        <div className="mt-3 space-y-2">
          {dossier.pending_verification.map((p) => (
            <div key={p.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <p className="font-mono text-sm font-semibold text-slate-900">{p.id}</p>
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                  {p.current_status}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-700">
                {p.item}（阶段 {p.phase}）
              </p>
              <p className="mt-1 text-xs text-slate-400">
                原因：{p.reason} · 所需证据 {p.required_evidence} · 负责角色 {p.required_role}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 四角色签署要求 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">四角色真实人工签署要求</h2>
      {dossier && dossier.signoff_requirements.length > 0 ? (
        <div className="mt-3 space-y-2">
          {dossier.signoff_requirements.map((r) => (
            <div
              key={r.required_role}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm"
            >
              <span className="font-mono text-slate-700">{r.required_role}</span>
              <span
                className={`rounded-full px-3 py-0.5 text-xs font-medium ${
                  r.is_satisfied
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-amber-100 text-amber-700"
                }`}
              >
                {r.current_status}
                {r.signed_by ? ` · ${r.signed_by}` : ""}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* 工程激活契约 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">工程激活契约</h2>
      {dossier ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-5 text-sm">
          <p className="text-slate-600">
            activation_allowed_for_human：
            <span
              className={`font-semibold ${
                dossier.contract.activation_allowed_for_human ? "text-emerald-600" : "text-red-600"
              }`}
            >
              {String(dossier.contract.activation_allowed_for_human)}
            </span>
            （AI 仅判定；真实启用须主理人在人类终端执行）
          </p>
          <p className="mt-2 text-slate-600">
            必需闸门（{dossier.contract.required_gates.length}）：
            <span className="font-mono text-slate-800">{dossier.contract.required_gates.join("、")}</span>
          </p>
          <p className="mt-1 text-slate-600">
            必需签署（{dossier.contract.required_signoffs.length}）：
            <span className="font-mono text-slate-800">{dossier.contract.required_signoffs.join("、")}</span>
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
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
        <input
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          placeholder="真实签署凭证坐标（必填：线下签署文档 / 工单 / 归档审批 ID）"
          value={signRef}
          onChange={(e) => setSignRef(e.target.value)}
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
        提醒：本页面为「生产激活证据就绪」只读控制台。Phase 3.9.6 不执行真实部署、不开启
        engineering_enabled、不自动 GO，也不提供任何 /activate 或 /deploy-production 端点。
        任何生产放行须主理人与专家线下提交真实证据并由真实责任人签署。
      </p>
    </section>
  );
}
