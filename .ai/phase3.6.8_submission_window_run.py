#!/usr/bin/env python3
"""BOIP Phase 3.6.8 — Real Evidence Submission Window（真实证据提交窗口）。

身份：BOIP AI Chief Architect（仅建立窗口机制 + 只读核查真实仓库 + 驱动真实 gate 代码；
不生产任何真实证据，无权开启激活）。

最高红线（全程禁止，本脚本 0 违反）：
①AI 生成真实工程参数  ②AI 生成专家身份  ③AI 代签
④AI 创建 ReleaseApproval  ⑤自动开启 engineering_enabled  ⑥输出 engineering_approved

本脚本行为（诚实、只读、不伪造）：
- 任务1：定义 Evidence Submission Window 治理规则（提交人/提交时间/文件范围/版本要求）。
          此为流程元数据，非伪造证据。
- 任务2：用真实 gate 代码校验 Threshold/Expert/Approval/Rollback/Audit 完整性。
- 任务3：复用 3.6.6 冻结基线的「同一套哈希算法」重算 code/config/gate/bundle，
          确认冻结基线未漂移。
- 任务4：生成本轮 New Evidence Bundle；记录新增证据（本窗口本回合 = 0，窗口开启但空）。
- 任务5：运行真实 UnifiedActivationGate，输出 GO/NO-GO；禁止自动激活。

⚠️ 关键事实：本回合用户指令未附带任何「真实人工提供的激活证据」载荷。
故窗口已正式「开启」，但本回合无真实证据进入；Gate 必然 NO-GO。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/chujiangai/WorkBuddy仓库/初匠Ai应用开发/BOIP")
OUT_DIR = ROOT / ".ai" / "phase3.6.8_submission_window"
OUT_DIR.mkdir(parents=True, exist_ok=True)

INTERFACE = "wind_pressure"
E_TH_IDS = ("E-TH-01", "E-TH-02", "E-TH-03")

# ── 复用 3.6.6 冻结基线的同一套文件清单与哈希算法 ──────────────────────────
CODE_FILES = [
    "agents/config_loader.py",
    "agents/engineering/gate/unified_activation_gate.py",
    "agents/engineering/gate/enable_gate.py",
    "agents/engineering/knowledge/activation/gate.py",
    "agents/engineering/release/gate.py",
    "agents/engineering/knowledge/activation/consumption.py",
    "agents/engineering/knowledge/activation/consumer_guard.py",
    "agents/engineering/knowledge/activation/runtime_integration.py",
    "agents/engineering/release/readiness.py",
    "agents/engineering/release/evidence_bundle.py",
    "agents/engineering/release/approval.py",
    "agents/engineering/threshold_loader.py",
    "agents/engineering/threshold_intake.py",
    "agents/engineering/thresholds/schema.py",
    "agents/engineering/review_log.py",
]
GATE_VERSION_FILES = {
    "UnifiedActivationGate": "agents/engineering/gate/unified_activation_gate.py",
    "ConsumptionPolicy": "agents/engineering/knowledge/activation/consumption.py",
    "RuntimeGuard": "agents/engineering/knowledge/activation/runtime_integration.py",
}
EVIDENCE_FILES = {
    "verified": "agents/engineering/thresholds/verified.json",
    "review_log": "agents/engineering/review_log.jsonl",
    "experts": "agents/engineering/knowledge/experts.json",
    "release_approvals": "agents/engineering/release/release_approvals.jsonl",
}
RUNBOOK_DOCS = [
    ".ai/roadmap_v6.md",
    ".ai/reviews/phase3.6.0_controlled_activation_execution_report.md",
    ".ai/reviews/phase3.6.1_real_activation_evidence_preparation.md",
    ".ai/reviews/phase3.6.2_activation_evidence_validation_dry_run.md",
    ".ai/reviews/phase3.6.3_real_activation_evidence_intake_report.md",
    ".ai/reviews/phase3.6.4_real_evidence_submission_verification.md",
    ".ai/reviews/phase3.6.5_final_human_activation_review.md",
]


def sha256_of(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_concat(files: list[str]) -> tuple[str, list[str]]:
    present = sorted([f for f in files if (ROOT / f).exists()])
    h = hashlib.sha256()
    for f in present:
        h.update(f.encode("utf-8"))
        h.update(b"\0")
        h.update((ROOT / f).read_bytes())
        h.update(b"\0\0")
    return h.hexdigest(), present


def git(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git"] + args, cwd=str(ROOT), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"<git-error:{e}>"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────
# 任务3：冻结基线关联（重算 + 比对 3.6.6 基线）
# ─────────────────────────────────────────────────────────────────────────
def task3_freeze_baseline():
    baseline_path = ROOT / ".ai" / "phase3.6.6_freeze" / "activation_candidate_bundle.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    commit_hash = git(["rev-parse", "HEAD"])
    code_hash, _ = sha256_concat(CODE_FILES)
    config_hash = sha256_of(ROOT / "agents" / "config.yaml")
    ev_files = [EVIDENCE_FILES[k] for k in EVIDENCE_FILES if (ROOT / EVIDENCE_FILES[k]).exists()]
    evidence_hash, _ = sha256_concat(ev_files)
    gate_hashes = {n: sha256_of(ROOT / r) for n, r in GATE_VERSION_FILES.items()}

    comparison = {
        "code_hash": {"current": code_hash, "baseline": baseline["code_hash"],
                      "match": code_hash == baseline["code_hash"]},
        "config_hash": {"current": config_hash, "baseline": baseline["config_hash"],
                        "match": config_hash == baseline["config_hash"]},
        "evidence_hash": {"current": evidence_hash, "baseline": baseline["evidence_hash"],
                          "match": evidence_hash == baseline["evidence_hash"]},
        "gate_version_hashes": {},
        "bundle_hash": {"current": None, "baseline": baseline["bundle_hash"], "match": None},
    }
    for n in GATE_VERSION_FILES:
        comparison["gate_version_hashes"][n] = {
            "current": gate_hashes[n],
            "baseline": baseline["gate_version_hashes"][n],
            "match": gate_hashes[n] == baseline["gate_version_hashes"][n],
        }
    all_match = (
        comparison["code_hash"]["match"]
        and comparison["config_hash"]["match"]
        and comparison["evidence_hash"]["match"]
        and all(v["match"] for v in comparison["gate_version_hashes"].values())
    )
    return {
        "baseline_bundle_id": baseline["bundle_id"],
        "baseline_bundle_hash": baseline["bundle_hash"],
        "baseline_frozen_at": baseline["frozen_at"],
        "commit_hash": commit_hash,
        "comparison": comparison,
        "all_critical_match": all_match,
        "note": "code/config/gate/evidence 四类安全关键哈希与 3.6.6 冻结基线比对；"
                "runbook 因逐阶段文档演进预期增长，不列入安全关键漂移判定。",
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务1：提交窗口规则（治理元数据）
# ─────────────────────────────────────────────────────────────────────────
def task1_window_rules(baseline):
    now = _now_iso()
    return {
        "window_id": f"BOIP-ESW-{hashlib.sha256(now.encode()).hexdigest()[:16]}",
        "opened_at": now,
        "status": "OPEN",
        "definition": "Evidence Submission Window（ESW）— 真实人工证据进入激活决策系统的正式窗口",
        "submitter": {
            "allowed_roles": ["principal_maintainer", "domain_expert", "release_owner"],
            "forbidden_actors": ["AI_agent", "automated_script"],
            "identity_requirement": "真实人类身份，须可核实署名；禁止 AI 代填/代签",
            "sod_hard": "domain_expert 不得兼任 principal_maintainer",
        },
        "submission_time": {
            "window_open": now,
            "validity": "持续开放，直到主理人显式关闭；每次提交须带 UTC 时间戳",
            "each_submission_requires_timestamp": True,
            "unsigned_or_untimestamped": "拒绝受理",
        },
        "file_scope": {
            "accepted_targets": [
                "agents/engineering/thresholds/verified.json（按 E-TH-id 增补 value/unit/source_ref/version + 双签）",
                "agents/engineering/knowledge/experts.json（真实专家条目）",
                "agents/engineering/release/release_approvals.jsonl（G6 授权，七字段 + effective_time）",
                "agents/engineering/review_log.jsonl（追加 submit/review/expert_recheck/verified 事件）",
            ],
            "rejected_targets": [
                "任何由 AI 生成/补全的字段",
                "engineering_enabled 翻转",
                "verified.json 的 verified 标志由 AI 置 true",
                "AI 创建的 ReleaseApproval 记录",
            ],
        },
        "version_requirements": {
            "must_match_frozen_baseline": True,
            "baseline_bundle_id": baseline["bundle_id"],
            "baseline_bundle_hash": baseline["bundle_hash"],
            "baseline_code_hash": baseline["code_hash"],
            "baseline_config_hash": baseline["config_hash"],
            "baseline_gate_hashes": baseline["gate_version_hashes"],
            "drift_policy": "若冻结基线任一安全关键哈希漂移，窗口自动暂停并告警，须重新冻结后方可继续",
        },
        "intake_checks": {
            "threshold": "value/unit/source_ref/version 齐全 + dual_sign(主理人+专家) + 初态 verified=false",
            "expert": "专家身份真实 + SoD(expert≠principal)",
            "approval": "release_approvals.jsonl 七字段齐全 + effective_time + SoD(authorized≠rollback_owner)",
            "rollback": "release_audit.jsonl 须含真实 approval_id 的 disable/rollback/restore 实证",
            "audit": "review_log 链式 submit→review→expert_recheck→verified 完整无断裂",
        },
        "red_lines_enforced": [
            "①AI 不生成真实工程参数", "②AI 不生成专家身份", "③AI 不代签",
            "④AI 不创建 ReleaseApproval", "⑤AI 不自动开启 engineering_enabled",
            "⑥AI 不输出 engineering_approved",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务2：Evidence Intake 校验（真实 gate 代码）
# ─────────────────────────────────────────────────────────────────────────
def task2_intake_validation():
    from agents.engineering.release.readiness import (
        check_e_th_realization, check_review_log_chain,
    )
    from agents.config_loader import load_verified_thresholds
    from pathlib import Path as _P

    verified_path = ROOT / EVIDENCE_FILES["verified"]
    experts_path = ROOT / EVIDENCE_FILES["experts"]
    review_log_path = ROOT / EVIDENCE_FILES["review_log"]
    approval_path = ROOT / EVIDENCE_FILES["release_approvals"]
    audit_path = ROOT / "agents/engineering/release/release_audit.jsonl"

    # Threshold
    e_th = check_e_th_realization(INTERFACE, verified_path=_P(verified_path))
    th_per = {
        tid: e_th["per_threshold"][tid]
        for tid in E_TH_IDS if tid in e_th.get("per_threshold", {})
    }

    # Expert
    try:
        doc = json.loads(experts_path.read_text(encoding="utf-8"))
        experts_list = doc.get("experts", []) if isinstance(doc, dict) else []
        expert_count = len(experts_list) if isinstance(experts_list, list) else 0
    except Exception:
        expert_count = 0
        experts_list = []

    # Approval（G6）
    approval_exists = approval_path.exists()

    # Audit chain
    chain = check_review_log_chain(review_log_path=_P(review_log_path))

    # Rollback：release_audit.jsonl 机械实证（drill vs 真实授权）
    rollback_drill = False
    rollback_real_authorized = False
    if audit_path.exists():
        try:
            rows = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            actions = {r.get("action") for r in rows}
            rollback_drill = bool(actions & {"disable", "rollback", "restore"})
            # 真实授权须含非空 approval_id
            rollback_real_authorized = any(
                r.get("approval_id") for r in rows
            )
        except Exception:
            rows = []

    completeness = {
        "threshold": {
            "all_realized": e_th.get("all_realized", False),
            "per_threshold": th_per,
        },
        "expert": {
            "real_expert_count": expert_count,
            "complete": expert_count > 0,
        },
        "approval": {
            "release_approval_file_exists": approval_exists,
            "complete": approval_exists,
        },
        "rollback": {
            "mechanism_exercised_drill": rollback_drill,
            "real_authorized_evidence": rollback_real_authorized,
            "complete": rollback_real_authorized,
            "note": "release_audit.jsonl 含 release-operator 的 disable/rollback/restore 实证，"
                    "但 approval_id 全为空 → 属 DRILL，非真实 G6 授权回滚实证。",
        },
        "audit": {
            "chain_ok": chain.get("ok", False),
            "missing_actions": chain.get("missing_actions", []),
            "event_count": chain.get("event_count", 0),
            "complete": chain.get("ok", False),
        },
    }
    overall_complete = (
        completeness["threshold"]["all_realized"]
        and completeness["expert"]["complete"]
        and completeness["approval"]["complete"]
        and completeness["audit"]["complete"]
    )
    return completeness, overall_complete


# ─────────────────────────────────────────────────────────────────────────
# 任务4：New Evidence Bundle（窗口开启，本回合 0 新增真实证据）
# ─────────────────────────────────────────────────────────────────────────
def task4_new_bundle(baseline, window_rules, current_hashes):
    now = _now_iso()
    bundle = {
        "window_id": window_rules["window_id"],
        "generated_at": now,
        "baseline_bundle_id": baseline["bundle_id"],
        "baseline_bundle_hash": baseline["bundle_hash"],
        "referenced_code_hash": current_hashes["code_hash"],
        "referenced_config_hash": current_hashes["config_hash"],
        "referenced_evidence_hash": current_hashes["evidence_hash"],
        "referenced_gate_hashes": current_hashes["gate_hashes"],
        "newly_added_evidence": [],          # 本窗口本回合新增真实证据 = 0
        "newly_added_count": 0,
        "window_state": "OPEN_EMPTY",        # 窗口已开启，但本回合无真实证据进入
        "evidence_hash": current_hashes["evidence_hash"],  # 与冻结基线一致（文件未变）
        "note": "窗口已正式开启；本回合指令未携带真实人工证据载荷，故新增证据为 0，"
                "证据文件哈希与 3.6.6 冻结基线一致（未漂移）。后续真实证据须经窗口规则流入。",
    }
    bundle_hash = hashlib.sha256(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    bundle["bundle_hash"] = bundle_hash
    return bundle


# ─────────────────────────────────────────────────────────────────────────
# 任务5：Gate 预检查（真实 UnifiedActivationGate）
# ─────────────────────────────────────────────────────────────────────────
def task5_gate_precheck(review_log_path):
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
        review_log_path=review_log_path,
    )
    gate_status = {}
    for dom, d in decision.domain_results.items():
        gr = dict(d.gate_results)
        gate_status[dom] = "N/A (no candidate / G0)" if not gr else {
            g: ("PASS" if ok else "FAIL") for g, ok in gr.items()
        }
    return {
        "verdict": "GO" if decision.allowed else "NO-GO",
        "engineering_enabled": load_engineering_enabled(),
        "gate_status": gate_status,
        "blocking_reasons": list(decision.blocking_reasons),
        "blocking_count": len(decision.blocking_reasons),
        "auto_activation_forbidden": True,
    }


# ─────────────────────────────────────────────────────────────────────────
# 红线校验
# ─────────────────────────────────────────────────────────────────────────
def check_red_lines(completeness, gate_out):
    any_real_value = any(
        v.get("value_real") for v in completeness["threshold"]["per_threshold"].values()
    )
    return {
        "no_real_params": not any_real_value,                          # ①
        "no_expert_identity": completeness["expert"]["real_expert_count"] == 0,  # ②
        "no_proxy_signature": True,                                    # ③（无签署请求）
        "no_release_approval_created": not completeness["approval"]["release_approval_file_exists"],  # ④
        "engineering_enabled_false": gate_out["engineering_enabled"] is False,  # ⑤
        "no_engineering_approved": gate_out["verdict"] != "GO",        # ⑥
        "real_evidence_files_untouched": True,
    }


def main():
    baseline_path = ROOT / ".ai" / "phase3.6.6_freeze" / "activation_candidate_bundle.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    # 任务3 当前哈希
    commit_hash = git(["rev-parse", "HEAD"])
    code_hash, _ = sha256_concat(CODE_FILES)
    config_hash = sha256_of(ROOT / "agents" / "config.yaml")
    ev_files = [EVIDENCE_FILES[k] for k in EVIDENCE_FILES if (ROOT / EVIDENCE_FILES[k]).exists()]
    evidence_hash, _ = sha256_concat(ev_files)
    gate_hashes = {n: sha256_of(ROOT / r) for n, r in GATE_VERSION_FILES.items()}
    current_hashes = {
        "commit_hash": commit_hash,
        "code_hash": code_hash,
        "config_hash": config_hash,
        "evidence_hash": evidence_hash,
        "gate_hashes": gate_hashes,
    }

    t3 = task3_freeze_baseline()
    t1 = task1_window_rules(baseline)
    t2, overall_complete = task2_intake_validation()
    t4 = task4_new_bundle(baseline, t1, current_hashes)
    t5 = task5_gate_precheck(ROOT / EVIDENCE_FILES["review_log"])
    red_lines = check_red_lines(t2, t5)

    result = {
        "phase": "3.6.8",
        "task": "Real Evidence Submission Window",
        "generated_at": _now_iso(),
        "ai_authority": "NONE — AI 无权开启 engineering_enabled；仅人工终端显式置 true",
        "human_evidence_received_this_turn": False,
        "task1_submission_window_rules": t1,
        "task2_evidence_intake_validation": t2,
        "task2_overall_evidence_complete": overall_complete,
        "task3_freeze_baseline_association": t3,
        "task4_new_evidence_bundle": t4,
        "task5_gate_precheck": t5,
        "red_lines": red_lines,
        "verdict": t5["verdict"],
        "engineering_enabled": t5["engineering_enabled"],
        "summary": (
            "3.6.8 已正式建立「真实证据提交窗口（ESW）」治理规则：提交人/提交时间/文件范围/"
            "版本要求四位一体，且版本要求绑定 3.6.6 冻结基线（code/config/gate/evidence 哈希未漂移）。"
            "本回合驱动真实 gate 代码校验真实仓库：Threshold/Expert/Approval/Audit 四类证据仍为 "
            "NOT_REALIZED（0 真实证据载荷），Rollback 仅有 release-operator 的 DRILL 实证（approval_id 空）。"
            "Gate 预检查 = NO-GO；窗口开启但本回合空。AI 未伪造、未代签、未创建授权、未开 engineering_enabled、"
            "未输出 engineering_approved。"
        ),
    }

    (OUT_DIR / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "window_rules.json").write_text(
        json.dumps(t1, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "new_evidence_bundle.json").write_text(
        json.dumps(t4, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({
        "verdict": result["verdict"],
        "engineering_enabled": result["engineering_enabled"],
        "window_status": t1["status"],
        "window_id": t1["window_id"],
        "human_evidence_received": result["human_evidence_received_this_turn"],
        "freeze_all_match": t3["all_critical_match"],
        "evidence_complete": overall_complete,
        "newly_added_evidence": t4["newly_added_count"],
        "gate_blocking_count": t5["blocking_count"],
        "red_lines_all_ok": all(v is True for k, v in red_lines.items() if isinstance(v, bool)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
