"use client";

/**
 * Phase 3.9.6 Task 18 —— 生产激活证据就绪控制台（只读 + 真实人工签署 + 真实证据接收链）。
 *
 * 设计红线（与后端同源，fail-closed）：
 * - 本页面仅面向**真实责任人（USER）**；请求头由 IdentityProvider 产出，
 *   而 IdentityProvider 只会为通过 assertHumanIdentity 的人类主体产出头（红线⑥）。
 * - **无自动上线按钮**：本页面不存在任何"一键部署 / 一键激活 / 自动 GO"入口。
 * - **无 AI 批准按钮**：AI 只生成就绪态只读快照，最终 GO 只能由真实责任人
 *   （production-owner / release-manager / security-owner / auditor）线下通过签署端点落
 *   AuditService 产生（红线②/⑧/⑩）。
 * - 人工只能签署**自己**的 GO / NO-GO / NEED_MORE_EVIDENCE，且必须填理由与真实签署凭证（留痕审计）。
 * - 取不到合法身份时页面**不降级**：直接显示错误并禁用一切写入动作。
 *
 * Layer A（只读就绪 dossier + 四角色签署，仓库派生）与 Layer B（真实人工提交的证据接收链：
 * intake-summary / evidence-list / evidence / evidence-decision / review-package / final-decision）
 * 正交、互不顶替；两者都只产出事实与人裁决，**不产出放行结论**。
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
type FinalOutcome = "go" | "no_go" | "defer";

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

const FINAL_OUTCOME_LABEL: Record<FinalOutcome, string> = {
  go: "GO（登记放行裁决）",
  no_go: "NO-GO（不放行）",
  defer: "DEFER（暂缓）",
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

/** Layer B：证据接收只读汇总（intake-summary）。 */
interface IntakeSummary {
  rc_id: string;
  required_types: string[];
  submitted_types: string[];
  missing_types: string[];
  structurally_validated_ids: string[];
  validation_failed_ids: string[];
  human_approved_ids: string[];
  human_rejected_ids: string[];
  awaiting_human_ids: string[];
  total_submissions: number;
  intake_complete: boolean;
  generated_at: string;
}

/** Layer B：已提交证据条目（evidence-list，只含引用/哈希/派生事实）。 */
interface EvidenceItem {
  submission_id: string;
  rc_id: string;
  evidence_type: string;
  title: string;
  content_reference: string;
  status: string;
  integrity_status: string;
  verification_status: string;
  computed_sha256: string | null;
  hash_match: boolean | null;
  structurally_valid: boolean;
  is_human_approved: boolean;
  is_human_rejected: boolean;
  awaiting_human_review: boolean;
  human_decision_by: string | null;
  human_decision_at: string | null;
  human_decision_reason: string | null;
  received_at: string;
}

/** Layer B：最终裁决登记簿快照（decision-ledger）。 */
interface EffectiveDecision {
  decision_id: string;
  rc_id: string;
  outcome: string;
  decided_by: string;
  decided_by_kind: string;
  decided_at: string;
  signature_reference: string;
  reason: string;
  reviewed_package_id: string;
  reviewed_package_digest: string;
  reviewed_package_readiness: string;
  is_go: boolean;
  is_blocking: boolean;
}

interface DecisionLedger {
  rc_id: string;
  total_decisions: number;
  effective_decision: EffectiveDecision | null;
  superseded_decisions: EffectiveDecision[];
  human_go_recorded: boolean;
  blocking_recorded: boolean;
  generated_at: string;
  note: string;
}

type Perm = "governance:release:read" | "governance:release:signoff";

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

function evidenceStatusTone(status: string): string {
  switch (status) {
    case "approved_by_human":
      return "bg-emerald-100 text-emerald-700";
    case "rejected_by_human":
      return "bg-red-100 text-red-700";
    case "structurally_validated":
    case "pending_human_evidence":
      return "bg-blue-100 text-blue-700";
    case "validation_failed":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

/** 真实责任人发起的写操作统一入口（强制 RELEASE_READ / RELEASE_SIGNOFF）。 */
async function authPost(path: string, permission: Perm, body: unknown): Promise<unknown> {
  const provider = getIdentityProvider();
  const me = await provider.getIdentity();
  requirePermission(me, permission);
  const headers = await provider.getAuthHeaders();
  const res = await fetch(
    `${API_BASE}${path}?rc_id=${encodeURIComponent(RC_ID)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    }
  );
  const text = await res.text().catch(() => "");
  if (!res.ok) throw new Error(`请求失败（${res.status}）${text ? `：${text}` : ""}`);
  return text ? JSON.parse(text) : null;
}

export default function GovernanceActivationPage(): JSX.Element {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [intake, setIntake] = useState<IntakeSummary | null>(null);
  const [ledger, setLedger] = useState<DecisionLedger | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);

  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [identity, setIdentity] = useState<GovernanceIdentity | null>(null);

  const [signRole, setSignRole] = useState<SignoffRole>("release-manager");
  const [signDecision, setSignDecision] = useState<SignoffDecision>("need_more_evidence");
  const [signReason, setSignReason] = useState<string>("");
  const [signRef, setSignRef] = useState<string>("");
  const [signResult, setSignResult] = useState<string>("");

  // Layer B —— 证据提交表单
  const [evType, setEvType] = useState<string>("");
  const [evTitle, setEvTitle] = useState<string>("");
  const [evContentRef, setEvContentRef] = useState<string>("");
  const [evOriginSystem, setEvOriginSystem] = useState<string>("");
  const [evOriginRef, setEvOriginRef] = useState<string>("");
  const [evDeclaredSha, setEvDeclaredSha] = useState<string>("");
  const [evResult, setEvResult] = useState<string>("");

  // Layer B —— 证据裁决控件
  const [decSubmissionId, setDecSubmissionId] = useState<string>("");
  const [decApproved, setDecApproved] = useState<boolean>(true);
  const [decReason, setDecReason] = useState<string>("");
  const [decResult, setDecResult] = useState<string>("");

  // Layer B —— 评审包 & 最终裁决
  const [rpPackageId, setRpPackageId] = useState<string>("");
  const [rpResult, setRpResult] = useState<string>("");
  const [lastPackageId, setLastPackageId] = useState<string>("");
  const [fdOutcome, setFdOutcome] = useState<FinalOutcome>("no_go");
  const [fdSignature, setFdSignature] = useState<string>("");
  const [fdReason, setFdReason] = useState<string>("");
  const [fdPackageId, setFdPackageId] = useState<string>("");
  const [fdConditions, setFdConditions] = useState<string>("");
  const [fdResult, setFdResult] = useState<string>("");

  const load = useCallback(async (): Promise<void> => {
    setError("");
    try {
      const provider = getIdentityProvider();
      const me = await provider.getIdentity();
      requirePermission(me, "governance:release:read");
      setIdentity(me);
      const headers = await provider.getAuthHeaders();
      const fetchJson = async (path: string): Promise<unknown> => {
        const res = await fetch(
          `${API_BASE}${path}?rc_id=${encodeURIComponent(RC_ID)}`,
          { headers }
        );
        if (!res.ok) throw new Error(`加载失败（${res.status}）${path}`);
        return res.json();
      };
      const [d, intakeSum, ledgerSnap, evList] = (await Promise.all([
        fetchJson("/governance/activation/readiness"),
        fetchJson("/governance/activation/intake-summary"),
        fetchJson("/governance/activation/decision-ledger"),
        fetchJson("/governance/activation/evidence-list"),
      ])) as [Dossier, IntakeSummary, DecisionLedger, EvidenceItem[]];
      setDossier(d);
      setIntake(intakeSum);
      setLedger(ledgerSnap);
      setEvidenceList(evList);
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

  const submitEvidence = async (): Promise<void> => {
    setBusy(true);
    setError("");
    setEvResult("");
    try {
      const type = evType.trim();
      const title = evTitle.trim();
      const ref = evContentRef.trim();
      const originSys = evOriginSystem.trim();
      const originRef = evOriginRef.trim();
      if (!type) throw new Error("证据类型必填");
      if (!title) throw new Error("证据标题必填");
      if (!ref) throw new Error("内容引用必填（只填引用坐标，勿填证据正文/密钥）");
      if (!originSys) throw new Error("来源系统必填");
      if (!originRef) throw new Error("来源引用必填");

      await authPost("/governance/activation/evidence", "governance:release:read", {
        evidence_type: type,
        title,
        content_reference: ref,
        origin_system: originSys,
        origin_reference: originRef,
        declared_sha256: evDeclaredSha.trim() || null,
        captured_at: null,
        chain_of_custody: [],
        recompute_hash: true,
      });
      setEvResult("证据已提交（仅结构接收，尚未经人工批准，不构成任何放行）。");
      void load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const recordEvidenceDecision = async (): Promise<void> => {
    setBusy(true);
    setError("");
    setDecResult("");
    try {
      const sid = decSubmissionId;
      const reason = decReason.trim();
      if (!sid) throw new Error("请选择要裁决的证据");
      if (!reason) throw new Error("裁决必须填写理由（留痕审计）");

      await authPost("/governance/activation/evidence-decision", "governance:release:signoff", {
        submission_id: sid,
        approved: decApproved,
        reason,
      });
      setDecResult(`已记录${decApproved ? "批准" : "驳回"}裁决（仅人工留痕，不解除任何闸门）。`);
      void load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "裁决失败");
    } finally {
      setBusy(false);
    }
  };

  const buildReviewPackage = async (): Promise<void> => {
    setBusy(true);
    setError("");
    setRpResult("");
    try {
      const pkg = (await authPost(
        "/governance/activation/review-package",
        "governance:release:read",
        { package_id: rpPackageId.trim() || null }
      )) as { package_id?: string; readiness?: string };
      const pid = pkg.package_id ?? "";
      setLastPackageId(pid);
      setFdPackageId((prev) => prev || pid);
      setRpResult(
        `评审包已生成（package_id=${pid}，就绪度=${pkg.readiness ?? "未知"}；仅材料≠裁决，不构成放行）。`
      );
      void load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成评审包失败");
    } finally {
      setBusy(false);
    }
  };

  const recordFinalDecision = async (): Promise<void> => {
    setBusy(true);
    setError("");
    setFdResult("");
    try {
      const sig = fdSignature.trim();
      const reason = fdReason.trim();
      if (!sig) throw new Error("最终裁决必须携带真实 signature_reference（必填）");
      if (!reason) throw new Error("最终裁决必须填写理由（必填）");

      await authPost("/governance/activation/final-decision", "governance:release:signoff", {
        outcome: fdOutcome,
        signature_reference: sig,
        reason,
        package_id: (fdPackageId.trim() || lastPackageId) || null,
        conditions: fdConditions.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      setFdResult(
        "最终裁决已登记（仅记录，不激活、不宣布 GO；真实生产启用须主理人在人类终端执行）。"
      );
      void load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "登记最终裁决失败");
    } finally {
      setBusy(false);
    }
  };

  const canSign = identity !== null && hasPermission(identity, "governance:release:signoff");
  const canRead = identity !== null && hasPermission(identity, "governance:release:read");

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
        只读查看激活就绪态、阻断器、待核验、四角色签署要求与工程激活契约；并可提交真实激活证据、
        对证据作人工裁决、生成评审包与登记最终裁决。本页面不部署、不激活、不自动放行；
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
          未取得责任人身份，一切写入动作已全部禁用。
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

      {/* 真实人工签署区（Layer A 唯一写入动作；无自动上线/AI 批准按钮） */}
      <h2 className="mt-10 text-xl font-semibold text-slate-800">真实人工签署（Layer A）</h2>
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

      {/* =====================================================================
          Layer B：真实人工证据接收链（T15）
          ===================================================================== */}

      {/* B1 证据接收汇总 */}
      <h2 className="mt-10 text-xl font-semibold text-slate-800">证据接收汇总（Layer B）</h2>
      {intake ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">已提交总数</p>
            <p className="mt-1 text-sm text-slate-800">{intake.total_submissions}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">结构校验通过</p>
            <p className="mt-1 text-sm text-slate-800">{intake.structurally_validated_ids.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">人工批准</p>
            <p className="mt-1 text-sm text-emerald-600">{intake.human_approved_ids.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">待人工复核</p>
            <p className="mt-1 text-sm text-blue-600">{intake.awaiting_human_ids.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">人工驳回</p>
            <p className="mt-1 text-sm text-red-600">{intake.human_rejected_ids.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">结构校验失败</p>
            <p className="mt-1 text-sm text-amber-600">{intake.validation_failed_ids.length}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">接收完成</p>
            <p
              className={`mt-1 text-sm font-semibold ${
                intake.intake_complete ? "text-emerald-600" : "text-amber-600"
              }`}
            >
              {String(intake.intake_complete)}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs uppercase tracking-wide text-slate-400">缺失类型</p>
            <p className="mt-1 text-sm text-slate-800">{intake.missing_types.length}</p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}
      {intake && (intake.required_types.length > 0 || intake.missing_types.length > 0) ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">必需证据类型</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {intake.required_types.map((t) => (
                <span
                  key={t}
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    intake.missing_types.includes(t)
                      ? "bg-amber-100 text-amber-700"
                      : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <p className="text-xs uppercase tracking-wide text-slate-400">缺失证据类型</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {intake.missing_types.length > 0 ? (
                intake.missing_types.map((t) => (
                  <span key={t} className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                    {t}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-400">无缺失</span>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* B2 最终裁决登记簿快照 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">最终裁决登记簿（Layer B）</h2>
      {ledger ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-5 text-sm">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">裁决总数</p>
              <p className="mt-1 text-slate-800">{ledger.total_decisions}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">已登记 GO</p>
              <p
                className={`mt-1 font-semibold ${
                  ledger.human_go_recorded ? "text-emerald-600" : "text-slate-600"
                }`}
              >
                {String(ledger.human_go_recorded)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">阻断已登记</p>
              <p className="mt-1 text-slate-800">{String(ledger.blocking_recorded)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">被取代裁决</p>
              <p className="mt-1 text-slate-800">{ledger.superseded_decisions.length}</p>
            </div>
          </div>
          {ledger.effective_decision ? (
            <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <p>
                当前有效裁决：
                <span className="font-medium text-slate-800">
                  {ledger.effective_decision.outcome}
                </span>
                （by {ledger.effective_decision.decided_by} · 绑定包{" "}
                {ledger.effective_decision.reviewed_package_id} · 就绪度{" "}
                {ledger.effective_decision.reviewed_package_readiness}）
              </p>
              <p className="mt-1 text-slate-400">
                注：human_go_recorded 仅表示真实人工已登记 GO 裁决，不等于系统已放行、更不等于已激活。
              </p>
            </div>
          ) : (
            <p className="mt-3 text-xs text-slate-400">暂无已登记裁决。</p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">加载中…</p>
      )}

      {/* B3 已提交证据列表 */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">
        已提交证据（{evidenceList.length}）
      </h2>
      {evidenceList.length > 0 ? (
        <div className="mt-3 space-y-2">
          {evidenceList.map((e) => (
            <div key={e.submission_id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <p className="font-mono text-sm font-semibold text-slate-900">
                  {e.submission_id}
                </p>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${evidenceStatusTone(
                    e.status
                  )}`}
                >
                  {e.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-700">
                [{e.evidence_type}] {e.title}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                引用 {e.content_reference} · 结构有效 {String(e.structurally_valid)} · 人工批准{" "}
                {String(e.is_human_approved)} · 人工驳回 {String(e.is_human_rejected)} · 待复核{" "}
                {String(e.awaiting_human_review)}
                {e.human_decision_by ? ` · 裁决人 ${e.human_decision_by}` : ""}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-400">暂无已提交证据。</p>
      )}

      {/* B4 证据提交表单（真实 USER + RELEASE_READ） */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">提交激活证据（Layer B）</h2>
      <p className="mt-2 text-sm text-slate-500">
        只提交<span className="font-medium">引用坐标</span>（本地路径 / 工单号 / 外部 URL / 线下件编号），
        系统只存引用与哈希、永不存证据原文（红线⑦）。提交仅结构接收，不视为采信。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block text-xs font-medium text-slate-600">
            证据类型（必填）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="如 staging_validation_report"
              value={evType}
              onChange={(e) => setEvType(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            证据标题（必填）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="简明描述"
              value={evTitle}
              onChange={(e) => setEvTitle(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            内容引用（必填，勿填正文/密钥）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="路径 / 工单号 / URL / 线下件编号"
              value={evContentRef}
              onChange={(e) => setEvContentRef(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            声明 SHA-256（可选）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="留空则由系统重算"
              value={evDeclaredSha}
              onChange={(e) => setEvDeclaredSha(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            来源系统（必填）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="如 test_ci / idp / manual"
              value={evOriginSystem}
              onChange={(e) => setEvOriginSystem(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            来源引用（必填）
            <input
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              placeholder="系统内坐标"
              value={evOriginRef}
              onChange={(e) => setEvOriginRef(e.target.value)}
            />
          </label>
        </div>
        {evResult ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {evResult}
          </p>
        ) : null}
        <button
          type="button"
          disabled={busy || !canRead}
          title={canRead ? undefined : "当前责任人无「发布只读」权限（governance:release:read）"}
          onClick={() => void submitEvidence()}
          className="mt-3 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "提交中…" : "提交证据"}
        </button>
      </div>

      {/* B5 证据裁决控件（真实 USER + RELEASE_SIGNOFF） */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">人工裁决证据（Layer B）</h2>
      <p className="mt-2 text-sm text-slate-500">
        对单条证据作<span className="font-medium">批准 / 驳回</span>裁决（唯一能产出 APPROVED_BY_HUMAN
        的路径）。结构校验失败的证据不得被批准；裁决不改变任何闸门状态（红线④⑨）。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <label className="block text-xs font-medium text-slate-600">
          选择证据（submission_id）
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={decSubmissionId}
            onChange={(e) => setDecSubmissionId(e.target.value)}
          >
            <option value="">— 请选择 —</option>
            {evidenceList.map((e) => (
              <option key={e.submission_id} value={e.submission_id}>
                {e.submission_id} · {e.evidence_type} · {e.status}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block text-xs font-medium text-slate-600">
          裁决
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={decApproved ? "approve" : "reject"}
            onChange={(e) => setDecApproved(e.target.value === "approve")}
          >
            <option value="approve">批准（APPROVED_BY_HUMAN）</option>
            <option value="reject">驳回（REJECTED_BY_HUMAN）</option>
          </select>
        </label>
        <textarea
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          rows={3}
          placeholder="请填写裁决理由（必填，留痕审计）"
          value={decReason}
          onChange={(e) => setDecReason(e.target.value)}
        />
        {decResult ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {decResult}
          </p>
        ) : null}
        <button
          type="button"
          disabled={busy || !canSign}
          title={canSign ? undefined : "当前责任人无「发布签署」权限（governance:release:signoff）"}
          onClick={() => void recordEvidenceDecision()}
          className="mt-3 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "提交中…" : "提交裁决"}
        </button>
      </div>

      {/* B6 生成评审包（真实 USER + RELEASE_READ） */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">生成评审包（Layer B · 材料≠裁决）</h2>
      <p className="mt-2 text-sm text-slate-500">
        汇总当前全部事实生成只读评审材料包，供真实责任人裁决。包就绪度上限
        <span className="font-medium"> READY_FOR_HUMAN_FINAL_REVIEW</span>，永不含 engineering_approved / Production GO。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <label className="block text-xs font-medium text-slate-600">
          评审包 ID（可选，留空自动生成）
          <input
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            placeholder="farp-xxxxxxxxxxxx"
            value={rpPackageId}
            onChange={(e) => setRpPackageId(e.target.value)}
          />
        </label>
        {rpResult ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {rpResult}
          </p>
        ) : null}
        <button
          type="button"
          disabled={busy || !canRead}
          title={canRead ? undefined : "当前责任人无「发布只读」权限（governance:release:read）"}
          onClick={() => void buildReviewPackage()}
          className="mt-3 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "生成中…" : "生成评审包"}
        </button>
      </div>

      {/* B7 登记最终裁决（真实 USER + RELEASE_SIGNOFF） */}
      <h2 className="mt-8 text-xl font-semibold text-slate-800">登记最终裁决（Layer B · 仅登记不激活）</h2>
      <p className="mt-2 text-sm text-slate-500">
        登记一条<span className="font-medium">已经发生</span>的真实人工最终裁决（记录，不是 AI 的结论）。
        GO 裁决要求绑定就绪的评审包，否则被拒；即便登记 GO，<span className="font-medium">engineering_enabled
        仍为 False</span>、激活由主理人在人类终端执行（红线①②⑤⑨⑩）。
      </p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
        <label className="block text-xs font-medium text-slate-600">
          裁决结果
          <select
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            value={fdOutcome}
            onChange={(e) => setFdOutcome(e.target.value as FinalOutcome)}
          >
            {(Object.keys(FINAL_OUTCOME_LABEL) as FinalOutcome[]).map((o) => (
              <option key={o} value={o}>
                {FINAL_OUTCOME_LABEL[o]}
              </option>
            ))}
          </select>
        </label>
        <input
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          placeholder="真实签署凭证坐标（必填：线下签署件 / 工单 / 邮件存档 ID）"
          value={fdSignature}
          onChange={(e) => setFdSignature(e.target.value)}
        />
        <textarea
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          rows={3}
          placeholder="请填写裁决理由（必填，留痕审计）"
          value={fdReason}
          onChange={(e) => setFdReason(e.target.value)}
        />
        <label className="mt-3 block text-xs font-medium text-slate-600">
          绑定评审包 ID（可选，自动复用上一步生成的包）
          <input
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
            placeholder="farp-xxxxxxxxxxxx"
            value={fdPackageId}
            onChange={(e) => setFdPackageId(e.target.value)}
          />
        </label>
        <textarea
          className="mt-3 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          rows={2}
          placeholder="附加条件（可选，每行一条）"
          value={fdConditions}
          onChange={(e) => setFdConditions(e.target.value)}
        />
        {fdResult ? (
          <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {fdResult}
          </p>
        ) : null}
        <button
          type="button"
          disabled={busy || !canSign}
          title={canSign ? undefined : "当前责任人无「发布签署」权限（governance:release:signoff）"}
          onClick={() => void recordFinalDecision()}
          className="mt-3 rounded-md bg-boip-primary-main px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "登记中…" : "登记最终裁决"}
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
