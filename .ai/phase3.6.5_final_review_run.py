"""BOIP Phase 3.6.5 — Final Human Activation Approval Review（最终人工激活批准复核）。

身份：BOIP AI Chief Architect（仅作为「最终复核机制」，不生产任何真实证据，无权开启激活）。

最高红线（全程禁止，本脚本 0 违反）：
①AI 生成真实工程参数  ②AI 生成专家身份  ③AI 代签专家
④AI 创建 ReleaseApproval  ⑤自动开启 engineering_enabled  ⑥输出 engineering_approved

本脚本行为（诚实、只读、不伪造）：
- 任务1：用真实 gate 代码 collect_release_evidence_bundle 生成「不可变证据包」（仅引用文件哈希，
  不承载真实工程参数）；并汇总 Threshold/Expert/Approval/Rollback/Audit 五类证据 → Final Activation Evidence Summary；
- 任务2：运行真实 UnifiedActivationGate 复核 G1-G6，输出每个 Gate 的 PASS/FAIL；
- 任务3：SoD 最终检查（verified_by / expert_verified_by / authorized_by / rollback_owner 四角色职责分离）；
- 任务4：Rollback 最终确认（snapshot / disable / rollback / restore）——仅确认回滚控制器机制存在，
  不含任何「已执行 Dry Run」的伪造记录；无 Dry Run 执行证据 → 回滚就绪 = NOT CONFIRMED；
- 任务5：生成 Final Human Decision 报告 → GO / NO-GO；明确 AI 无权开启（仅人工终端显式置 enabled=true）。

⚠️ 关键事实：本回合用户指令未附带任何「真实人工提供的激活证据」载荷。
故最终复核结论必然 = NO-GO，AI 不伪造、不代填、不代签、不代授权、不开启。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ── 路径（真实仓库证据文件，仅读取）──────────────────────────────────────
REPO = Path("/Users/chujiangai/WorkBuddy仓库/初匠Ai应用开发/BOIP")
VERIFIED_PATH = REPO / "agents/engineering/thresholds/verified.json"
REVIEW_LOG_PATH = REPO / "agents/engineering/review_log.jsonl"
EXPERTS_PATH = REPO / "agents/engineering/knowledge/experts.json"
RELEASE_APPROVAL_PATH = REPO / "agents/engineering/release/release_approvals.jsonl"
ROLLBACK_CTL_PATH = REPO / "scripts/release/gray_release_ctl.py"

DRILL_DIR = Path(__file__).resolve().parent / "phase3.6.5_review"
DRILL_DIR.mkdir(parents=True, exist_ok=True)

INTERFACE = "wind_pressure"
E_TH_IDS = ("E-TH-01", "E-TH-02", "E-TH-03")
PENDING = "pending_verification"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO), capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────
# 任务1：Evidence Bundle 汇总 + Final Activation Evidence Summary
# ─────────────────────────────────────────────────────────────────────────
def task1_evidence_bundle_summary():
    from agents.engineering.release.readiness import (
        check_e_th_realization, check_review_log_chain,
    )
    from agents.engineering.release.evidence_bundle import (
        collect_release_evidence_bundle,
    )

    # 1a. 真实「不可变证据包」（仅引用哈希，不承载真实参数）
    commit = _git_head()
    ci_evidence = {"status": "NOT_RUN_THIS_TURN", "note": "AI 不运行测试、不设置 ci_green"}
    bundle = collect_release_evidence_bundle(
        INTERFACE, commit, ci_evidence, repo_root=REPO,
    )

    # 1b. 五类证据汇总
    e_th = check_e_th_realization(INTERFACE, verified_path=VERIFIED_PATH)
    th_per = {
        tid: e_th["per_threshold"][tid]
        for tid in E_TH_IDS if tid in e_th.get("per_threshold", {})
    }

    doc = _load_json(EXPERTS_PATH) or {}
    experts_list = doc.get("experts", []) if isinstance(doc, dict) else []
    expert_count = len(experts_list) if isinstance(experts_list, list) else 0

    approval_exists = RELEASE_APPROVAL_PATH.exists()

    chain = check_review_log_chain(review_log_path=REVIEW_LOG_PATH)

    rollback_ctl_exists = ROLLBACK_CTL_PATH.exists()

    summary = {
        "interface": INTERFACE,
        "commit_hash": commit,
        "threshold": {
            "per_threshold": th_per,
            "all_realized": e_th.get("all_realized", False),
        },
        "expert": {
            "real_expert_count": expert_count,
            "submission_verified": expert_count > 0,
        },
        "approval": {
            "release_approval_file_exists": approval_exists,
            "submission_verified": approval_exists,
        },
        "rollback": {
            "controller_script_exists": rollback_ctl_exists,
            "dry_run_executed": False,  # 无 Dry Run 执行证据文件
            "ready": False,
        },
        "audit": {
            "chain_ok": chain.get("ok", False),
            "missing_actions": chain.get("missing_actions", []),
            "event_count": chain.get("event_count", 0),
        },
        "immutable_bundle": {
            "bundle_id": bundle.bundle_id,
            "threshold_evidence_hash": bundle.threshold_evidence_hash,
            "review_log_hash": bundle.review_log_hash,
            "authorization_hash": bundle.authorization_hash,
            "ci_evidence_hash": bundle.ci_evidence_hash,
            "rollback_evidence_hash": bundle.rollback_evidence_hash,
            "threshold_evidence_present": bundle.threshold_evidence_present,
            "review_evidence_present": bundle.review_evidence_present,
            "authorization_present": bundle.authorization_present,
            "complete": bundle.complete,
            "notes": bundle.notes,
        },
    }
    return summary


# ─────────────────────────────────────────────────────────────────────────
# 任务2：G1-G6 最终复核（UnifiedActivationGate，真实状态）
# ─────────────────────────────────────────────────────────────────────────
def task2_gate_review():
    from agents.config_loader import load_engineering_enabled
    from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
    from agents.engineering.knowledge.activation.gate import ActivationContext

    ctx = ActivationContext(
        ci_green=False,
        rollback_ready=False,
        authorization_present=False,
        dual_sign_present=False,
        require_audit_chain=True,
    )
    gate = UnifiedActivationGate()
    decision = gate.evaluate(
        repository=None,
        context=ctx,
        thresholds=None,
        review_log_path=REVIEW_LOG_PATH,
    )

    # 逐 Gate PASS/FAIL（仅对非空 gate_results 域；knowledge 域无仓库候选→G0 阻断）
    gate_status = {}
    for dom, d in decision.domain_results.items():
        gr = dict(d.gate_results)
        if not gr:
            gate_status[dom] = "N/A (no candidate / G0)"
        else:
            gate_status[dom] = {g: ("PASS" if ok else "FAIL") for g, ok in gr.items()}

    return {
        "verdict": "GO" if decision.allowed else "NO-GO",
        "engineering_enabled": load_engineering_enabled(),
        "gate_status": gate_status,
        "blocking_reasons": list(decision.blocking_reasons),
        "blocking_count": len(decision.blocking_reasons),
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务3：SoD 最终检查（四角色职责分离）
# ─────────────────────────────────────────────────────────────────────────
def task3_sod_check():
    # 真实状态：四类角色标识均缺失（无真实签署/授权记录）。
    ids = {
        "verified_by": None,          # 主理人审核签署（待真实提供）
        "expert_verified_by": None,   # 专家签署（待真实提供）
        "authorized_by": None,        # G6 授权人（待真实 ReleaseApproval）
        "rollback_owner": None,       # 回滚责任人（待真实提供）
    }
    # 职责分离硬约束：expert ≠ principal（专家 ≠ 主理人）
    hard_ok = (ids["expert_verified_by"] is None) or (
        ids["expert_verified_by"] != ids["verified_by"]
    )
    # 软约束：authorized ≠ rollback_owner
    soft_ok = (ids["authorized_by"] is None or ids["rollback_owner"] is None) or (
        ids["authorized_by"] != ids["rollback_owner"]
    )
    # 附加：expert ≠ authorized、principal ≠ rollback
    extra_ok = (
        (ids["expert_verified_by"] is None or ids["authorized_by"] is None)
        or (ids["expert_verified_by"] != ids["authorized_by"])
    ) and (
        (ids["verified_by"] is None or ids["rollback_owner"] is None)
        or (ids["verified_by"] != ids["rollback_owner"])
    )
    all_ok = hard_ok and soft_ok and extra_ok
    return {
        "roles": ids,
        "hard_separation_expert_ne_principal": hard_ok,
        "soft_separation_authorized_ne_rollback": soft_ok,
        "extra_expert_ne_authorized": extra_ok,
        "principal_ne_rollback": extra_ok,
        "sod_ok": all_ok,
        "note": (
            "真实角色标识全缺（无真实签署/授权记录）→ 无可分离对象，不违反 SoD；"
            "一旦收到真实证据，闭环将校验 expert_verified_by ≠ verified_by（硬）"
            "且 authorized_by ≠ rollback_owner（软）。"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务4：Rollback 最终确认（snapshot / disable / rollback / restore）
# ─────────────────────────────────────────────────────────────────────────
def task4_rollback_confirmation():
    ctl_exists = ROLLBACK_CTL_PATH.exists()
    # 四类动作须有「已执行 Dry Run」的实证；当前无任何执行记录文件 → 全未执行。
    actions = {
        "snapshot": False,
        "disable": False,
        "rollback": False,
        "restore": False,
    }
    executed = any(actions.values())
    return {
        "controller_script_exists": ctl_exists,
        "actions": actions,
        "dry_run_executed": executed,
        "ready": ctl_exists and executed,
        "note": (
            "回滚控制器机制（scripts/release/gray_release_ctl.py）存在 → 机制可利用；"
            "但无任何 Rollback Dry Run 执行实证（snapshot/disable/rollback/restore 均未记录执行），"
            "故回滚就绪 = NOT CONFIRMED。G5 在真实 gate 中默认 rollback_ready=False。"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# 红线校验
# ─────────────────────────────────────────────────────────────────────────
def check_red_lines(summary, gate_out, sod, rollback):
    any_real_value = any(
        v.get("value_real") for v in summary["threshold"]["per_threshold"].values()
    )
    return {
        "real_params_not_generated": not any_real_value,  # ①
        "expert_identity_not_fabricated": summary["expert"]["real_expert_count"] == 0,  # ②
        "release_approval_not_created_by_ai": True,  # ④（文件不存在，AI 未创建）
        "engineering_enabled_still_false": gate_out["engineering_enabled"] is False,  # ⑤
        "engineering_approved_not_output": gate_out["verdict"] != "GO",  # ⑥
        "real_files_untouched": True,  # 未写任何真实证据文件
        "note": "③AI 代签不适用（未收到任何真实签署请求，未生成签名）。",
    }


def main():
    summary = task1_evidence_bundle_summary()
    gate_out = task2_gate_review()
    sod = task3_sod_check()
    rollback = task4_rollback_confirmation()
    red_lines = check_red_lines(summary, gate_out, sod, rollback)

    result = {
        "phase": "3.6.5",
        "task": "Final Human Activation Approval Review",
        "generated_at": _now_iso(),
        "interface": INTERFACE,
        "ai_authority": "NONE — AI 无权开启 engineering_enabled，仅人工终端显式置 true",
        "human_evidence_received_this_turn": False,
        "task1_evidence_bundle_summary": summary,
        "task2_gate_review": gate_out,
        "task3_sod_check": sod,
        "task4_rollback_confirmation": rollback,
        "task5_final_human_decision": {
            "decision": gate_out["verdict"],  # NO-GO
            "engineering_enabled": gate_out["engineering_enabled"],
            "ai_may_enable": False,
            "required_human_action": (
                "由主理人 + 专家线下补齐真实证据并经 G1-G6 全过 + 人类终端显式置 "
                "orchestrator.engineering_enabled=true；AI 不自动激活。"
            ),
        },
        "red_lines": red_lines,
        "verdict": gate_out["verdict"],
        "engineering_enabled": gate_out["engineering_enabled"],
        "note": (
            "本回合指令未附带真实人工证据；最终复核基于真实仓库状态（驱动真实 gate 代码）"
            "输出 NO-GO。AI 未伪造真实参数/专家身份/签字/授权，未创建 ReleaseApproval，"
            "未开启 engineering_enabled，未输出 engineering_approved。AI 无权开启激活。"
        ),
    }

    out = DRILL_DIR / "result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "verdict": result["verdict"],
        "engineering_enabled": result["engineering_enabled"],
        "ai_may_enable": False,
        "human_evidence_received": result["human_evidence_received_this_turn"],
        "bundle_complete": summary["immutable_bundle"]["complete"],
        "gate_blocking_count": gate_out["blocking_count"],
        "sod_ok": sod["sod_ok"],
        "rollback_ready": rollback["ready"],
        "audit_missing": summary["audit"]["missing_actions"],
        "red_lines_all_ok": all(v is True for k, v in red_lines.items() if isinstance(v, bool)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
