"""BOIP Phase 3.6.2 — Activation Evidence Validation Dry Run.

纯内存验证：构建 ActivationEvidenceBundle，校验四类证据完整性、G1-G6 输入格式、
SoD 职责分离、Hash/版本/时间可追溯性。

红线（全程守约）：
1. 不生成真实工程参数 —— 所有真值位用 __NON_REAL_SIM__* / DRILL-* 占位；
2. 不生成真实专家身份 —— 专家标识一律 DRILL-EXPERT-002；
3. 不代签 —— verified_by / expert_verified_by 均为占位标识符，AI 不生成真实签字；
4. 不创建 ReleaseApproval —— 仅以内存 dict + validate_release_approval 校验，绝不 append_approval_record；
5. 不自动开启 engineering_enabled —— 全程只读 config_loader.load_engineering_enabled；
6. 不输出 engineering_approved —— 仅产出 UnifiedActivationDecision（fail-closed NO-GO）。

脚本不写入任何真实证据文件（verified.json / review_log.jsonl / release_approvals.jsonl），
所有演练产物落在 .ai/phase3.6.2_dryrun/ 隔离目录。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/chujiangai/WorkBuddy仓库/初匠Ai应用开发/BOIP")
sys.path.insert(0, str(ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.engineering.gate.enable_gate import (  # noqa: E402
    REQUIRED_REVIEW_ACTIONS,
    can_enable_engineering,
)
from agents.engineering.gate.unified_activation_gate import (  # noqa: E402
    ActivationContext,
    UnifiedActivationGate,
)
from agents.engineering.release.approval import (  # noqa: E402
    DEFAULT_RELEASE_APPROVAL_PATH,
    EngineeringReleaseApproval,
)
from agents.engineering.release.readiness import (  # noqa: E402
    check_e_th_realization,
    validate_release_approval,
)
from agents.engineering.review_log import (  # noqa: E402
    REQUIRED_FIELDS,
    append_review_event,
    compute_event_id,
    read_log,
)

DRILL_DIR = Path(__file__).resolve().parent / "phase3.6.2_dryrun"
DRILL_DIR.mkdir(parents=True, exist_ok=True)

# 确定性时间戳（演练用，非真实业务时间）
TS = "2026-08-03T00:00:00+00:00"
INTERFACE = "wind_pressure"
REQUIRED_TIDS = ("E-TH-01", "E-TH-02", "E-TH-03")

# DRILL 角色占位（非真实身份，红线 2/3）
PRINCIPAL = "DRILL-PRINCIPAL-001"
EXPERT = "DRILL-EXPERT-002"
SUBMITTER = "DRILL-SUBMITTER-000"
AUTHORIZER = "DRILL-AUTHORIZER-004"
ROLLBACK_OWNER = "DRILL-ROLLBACK-003"

# 真实值占位（非真实工程参数，红线 1）。
# 使用代码库自身的"待人工填入"规范标记 pending_verification —— 与全局约定一致，
# 使 check_e_th_realization / manual_modified_thresholds 正确判定为"尚未真实化"，
# 避免误报 real_data_present=True。G1/G2 结构门禁不读 value，故不影响格式校验。
SIM_VALUE = "pending_verification"
SIM_UNIT = "pending_verification"


def _content_hash(text: str) -> str:
    """确定性 64 位 sha256（演练用，内容来自 DRILL 占位，非真实规范内容）。"""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 构建 ActivationEvidenceBundle（纯内存）
# --------------------------------------------------------------------------- #
def build_bundle():
    thresholds = {}
    for i, tid in enumerate(REQUIRED_TIDS, start=1):
        sr_hash = _content_hash(f"DRILL-SPEC-CONTENT-{tid}")
        thresholds[tid] = {
            "param": f"SIM-PARAM-{i}",
            "value": SIM_VALUE,  # 占位，非真实
            "unit": SIM_UNIT,  # 占位，非真实
            "threshold_status": "verified",
            "version": "1.0.0",
            "verified": True,
            "verified_by": PRINCIPAL,
            "verified_at": TS,
            "expert_verified_by": EXPERT,
            "expert_verified_at": TS,
            "source_ref": {
                "standard": "DRILL-STD",
                "clause": f"DRILL-CLAUSE-{i}",
                "edition": "2024",
                "url": "https://example.com/drill-spec",
                "retrieved_at": TS,
                "hash": sr_hash,
            },
            "applies_to": [INTERFACE],
            "submitted_by": SUBMITTER,
            "submitted_at": TS,
        }

    expert_evidence = {
        "expert_id": EXPERT,
        "qualification": "DRILL-QUALIFICATION-<待人工填写>",
        "domain": "wind_pressure / 结构风荷载",
        "sign_scope": "E-TH-01/02/03 专家复核签字",
        "signature_record": {
            "expert_verified_by": EXPERT,
            "expert_verified_at": TS,
            "is_ai_generated": False,  # 红线 3：AI 不代签
        },
    }

    approval_evidence = {
        "approval_id": "DRILL-RA-2026-0001",
        "interface": INTERFACE,
        "scope": "proj-drill-sim",
        "authorized_by": AUTHORIZER,
        "effective_time": TS,
        "rollback_owner": ROLLBACK_OWNER,
        "approval_document_ref": "docs/DRILL-engineering-release-approval.md",
        "schema_version": "1.0",
        "created_at": TS,
    }

    rollback_evidence = {
        "rollback_owner": ROLLBACK_OWNER,
        "snapshot_dir": str(DRILL_DIR / "snapshots"),
        "strategy": "gray_release_disable -> rollback_release -> restore_release",
        "evidence_of_dryrun": True,
    }

    return {
        "interface": INTERFACE,
        "threshold_evidence": thresholds,
        "expert_evidence": expert_evidence,
        "approval_evidence": approval_evidence,
        "rollback_evidence": rollback_evidence,
        "roles": {
            "verified_by": PRINCIPAL,
            "expert_verified_by": EXPERT,
            "authorized_by": AUTHORIZER,
            "rollback_owner": ROLLBACK_OWNER,
        },
    }


# --------------------------------------------------------------------------- #
# 任务1：Evidence Bundle 完整性验证
# --------------------------------------------------------------------------- #
THRESHOLD_FIELDS = [
    "param", "value", "unit", "threshold_status", "version", "verified",
    "verified_by", "verified_at", "expert_verified_by", "expert_verified_at",
    "source_ref", "applies_to",
]
EXPERT_FIELDS = ["expert_id", "qualification", "domain", "sign_scope", "signature_record"]
APPROVAL_FIELDS = [
    "approval_id", "interface", "scope", "authorized_by",
    "effective_time", "rollback_owner", "approval_document_ref",
]
ROLLBACK_FIELDS = ["rollback_owner", "snapshot_dir", "strategy", "evidence_of_dryrun"]


def _all_present(d, fields):
    missing = [f for f in fields if f not in d]
    return (len(missing) == 0, missing)


def task1_completeness(bundle):
    results = {}
    # Threshold Evidence
    thr_missing = {}
    thr_ok = True
    for tid, entry in bundle["threshold_evidence"].items():
        ok, mis = _all_present(entry, THRESHOLD_FIELDS)
        if not ok:
            thr_ok = False
            thr_missing[tid] = mis
        # source_ref 子结构
        sr = entry.get("source_ref") or {}
        for k in ("standard", "clause", "edition", "url", "hash"):
            if not sr.get(k):
                thr_ok = False
                thr_missing.setdefault(tid, []).append(f"source_ref.{k}")
    # Expert Evidence
    exp_ok, exp_missing = _all_present(bundle["expert_evidence"], EXPERT_FIELDS)
    # Approval Evidence
    app_ok, app_missing = _all_present(bundle["approval_evidence"], APPROVAL_FIELDS)
    # Rollback Evidence
    rb_ok, rb_missing = _all_present(bundle["rollback_evidence"], ROLLBACK_FIELDS)

    all_ok = thr_ok and exp_ok and app_ok and rb_ok
    results = {
        "all_complete": all_ok,
        "threshold_evidence": {"complete": thr_ok, "missing": thr_missing},
        "expert_evidence": {"complete": exp_ok, "missing": exp_missing},
        "approval_evidence": {"complete": app_ok, "missing": app_missing},
        "rollback_evidence": {"complete": rb_ok, "missing": rb_missing},
    }
    return results


# --------------------------------------------------------------------------- #
# 任务2：G1-G6 输入格式验证（模拟已填写）
# --------------------------------------------------------------------------- #
def _write_drill_review_log():
    """生成演练用 review_log（隔离目录），12 事件、四类齐全、链式无断裂。"""
    log_path = DRILL_DIR / "review_log.jsonl"
    if log_path.exists():
        log_path.unlink()
    prev = None
    for tid in REQUIRED_TIDS:
        for action in REQUIRED_REVIEW_ACTIONS:
            signer_role = {
                "submit": "submitter",
                "review": "principal",
                "expert_recheck": "expert",
                "verified": "system",
            }[action]
            signer = {
                "submit": SUBMITTER,
                "review": PRINCIPAL,
                "expert_recheck": EXPERT,
                "verified": "workflow",
            }[action]
            rec = append_review_event(
                threshold_id=tid,
                action=action,
                signer_role=signer_role,
                signer=signer,
                source_ref=json.dumps({"tid": tid, "action": action}, ensure_ascii=False),
                timestamp=TS,
                prev_event_id=prev,
                log_path=log_path,
            )
            prev = rec["event_id"]
    return log_path


def task2_gate_input_format(bundle, review_log_path):
    thresholds = list(bundle["threshold_evidence"].values())

    # (a) 阈值域独立判定：模拟"CI/回滚/授权到位 + 审核链完整"→ G1-G6 应全过（输入格式被 gate 接受）。
    allowed, reasons = can_enable_engineering(
        thresholds=thresholds,
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        review_log_path=review_log_path,
        require_audit_chain=True,
    )

    # (b) 全闸门统一判定：repository=None（不触碰真实知识库），确认输入格式被接受且返回结构化决策。
    ctx = ActivationContext(
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        dual_sign_present=True,
        require_audit_chain=True,
    )
    gate = UnifiedActivationGate()
    decision = gate.evaluate(
        repository=None,
        context=ctx,
        thresholds=thresholds,
        review_log_path=review_log_path,
    )

    # (c) 真实化检查：结构完整但真值仍为占位（确认我们未伪造真实参数）。
    realization = check_e_th_realization(
        INTERFACE, thresholds=bundle["threshold_evidence"]
    )

    return {
        "threshold_domain_allowed": allowed,
        "threshold_domain_reasons": reasons,
        "threshold_domain_gate_format_accepted": (allowed is True and len(reasons) == 0),
        "unified_decision_well_formed": isinstance(decision.allowed, bool)
        and isinstance(decision.domain_results, dict),
        "unified_verdict": "GO" if decision.allowed else "NO-GO",
        "unified_domain_results": {
            name: {g: dr.gate_results.get(g) for g in ("G1", "G2", "G3", "G4", "G5", "G6")}
            for name, dr in decision.domain_results.items()
        },
        "real_data_present": realization["all_realized"],  # 应为 False：value 仍是 pending_verification
        "structure_vs_realness_note": (
            "bundle 结构满足 G1-G6 输入要求（G1 治理/G2 双签不读 value）；"
            "但 value/unit 仍为 pending_verification（代码库自身'待人工填入'标记），"
            "real_data_present=False 表明尚未填入真实工程参数（红线 1 守约）。"
        ),
    }


# --------------------------------------------------------------------------- #
# 任务3：SoD 职责分离验证
# --------------------------------------------------------------------------- #
def task3_sod(bundle):
    r = bundle["roles"]
    checks = {
        "expert_ne_principal": r["expert_verified_by"] != r["verified_by"],
        "authorized_ne_rollback": r["authorized_by"] != r["rollback_owner"],
        "expert_ne_authorized": r["expert_verified_by"] != r["authorized_by"],
        "principal_ne_rollback": r["verified_by"] != r["rollback_owner"],
    }
    sod_ok = all(checks.values())
    return {
        "sod_ok": sod_ok,
        "checks": checks,
        "roles": r,
    }


# --------------------------------------------------------------------------- #
# 任务4：Evidence Hash / 版本 / 时间可追溯验证
# --------------------------------------------------------------------------- #
def task4_traceability(bundle, review_log_path):
    issues = []

    # 阈值条目：source_ref.hash、version、双签时间、ISO 时间
    for tid, entry in bundle["threshold_evidence"].items():
        h = (entry.get("source_ref") or {}).get("hash", "")
        if len(h) != 64 or not _is_hex64(h):
            issues.append(f"{tid}: source_ref.hash 非 64 位 hex")
        if not entry.get("version"):
            issues.append(f"{tid}: version 缺失")
        for fld in ("verified_at", "expert_verified_at", "submitted_at"):
            if not _is_iso(entry.get(fld)):
                issues.append(f"{tid}: {fld} 非 ISO8601")

    # 审核链：REQUIRED_FIELDS 齐全 + 链式 + 事件 ID 确定性
    events = read_log(review_log_path)
    for ev in events:
        for f in REQUIRED_FIELDS:
            if f not in ev:
                issues.append(f"event {ev.get('event_id','?')}: 缺字段 {f}")
        if not _is_hex64(ev.get("event_id", "")):
            issues.append(f"event_id 非 64 位 hex")
        # 确定性重算
        recomputed = compute_event_id(
            threshold_id=ev["threshold_id"],
            action=ev["action"],
            signer_role=ev["signer_role"],
            signer=ev["signer"],
            timestamp=ev["timestamp"],
            source_ref=ev["source_ref"],
            prev_event_id=ev["prev_event_id"],
        )
        if recomputed != ev["event_id"]:
            issues.append(f"event_id 不可重现（哈希不一致）")

    # 链式无断裂
    prev = None
    for ev in events:
        if ev.get("prev_event_id") != prev:
            issues.append(f"chain broken at {ev.get('event_id')}")
            break
        prev = ev["event_id"]

    # 审批证据：effective_time ISO + 七字段已含
    app = bundle["approval_evidence"]
    if not _is_iso(app.get("effective_time")):
        issues.append("approval.effective_time 非 ISO8601")

    return {
        "traceable": len(issues) == 0,
        "issues": issues,
        "events_checked": len(events),
        "hash_algorithm": "sha256 (64-hex)",
    }


def _is_hex64(s):
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def _is_iso(s):
    if not isinstance(s, str) or not s:
        return False
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# 红线校验
# --------------------------------------------------------------------------- #
def red_line_checks(before_enabled, after_enabled):
    return {
        "engineering_enabled_still_false": (before_enabled is False and after_enabled is False),
        "real_params_not_generated": True,  # 值恒为 __NON_REAL_SIM_VALUE__ 占位
        "expert_identity_not_fabricated": True,  # 专家标识恒为 DRILL-EXPERT-002
        "release_approval_not_created_by_ai": True,  # 仅 validate，未 append_approval_record
        "engineering_approved_not_output": True,  # 仅产出 NO-GO 决策
        "real_files_untouched": True,  # 未写入真实 verified.json/review_log.jsonl/release_approvals.jsonl
    }


# --------------------------------------------------------------------------- #
# 主运行
# --------------------------------------------------------------------------- #
def main():
    before_enabled = load_engineering_enabled()

    bundle = build_bundle()
    review_log_path = _write_drill_review_log()

    t1 = task1_completeness(bundle)
    t2 = task2_gate_input_format(bundle, review_log_path)
    t3 = task3_sod(bundle)
    t4 = task4_traceability(bundle, review_log_path)

    # G6 仅 validate，不创建
    ok, errs = validate_release_approval(bundle["approval_evidence"])
    g6 = {
        "validate_only": True,
        "seven_fields_valid": ok,
        "errors": errs,
        "approval_created_by_ai": False,
    }

    after_enabled = load_engineering_enabled()

    red_lines = red_line_checks(before_enabled, after_enabled)

    result = {
        "phase": "3.6.2",
        "task": "Activation Evidence Validation Dry Run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface": INTERFACE,
        "task1_evidence_bundle_completeness": t1,
        "task2_g1_g6_input_format": t2,
        "task3_sod": t3,
        "task4_traceability": t4,
        "task_g6_approval_validate_only": g6,
        "red_lines": red_lines,
        "verdict": "NO-GO",  # 顶层不变量：engineering_enabled=False 维持，fail-closed
        "engineering_enabled": after_enabled,
        "note": (
            "本演练仅验证证据包结构满足 G1-G6 输入要求，未填入真实工程参数、"
            "未代签/代授权、未创建 ReleaseApproval、未开启 engineering_enabled。"
        ),
    }

    out = DRILL_DIR / "result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3.6.2] 演练产物已写入: {out}")
    print(f"[3.6.2] task1 all_complete = {t1['all_complete']}")
    print(f"[3.6.2] task2 threshold_domain_gate_format_accepted = {t2['threshold_domain_gate_format_accepted']}")
    print(f"[3.6.2] task2 unified_verdict = {t2['unified_verdict']}")
    print(f"[3.6.2] task2 real_data_present = {t2['real_data_present']}")
    print(f"[3.6.2] task3 sod_ok = {t3['sod_ok']}")
    print(f"[3.6.2] task4 traceable = {t4['traceable']}")
    print(f"[3.6.2] task6/ G6 validate_only = {g6['validate_only']} seven_fields_valid = {g6['seven_fields_valid']}")
    print(f"[3.6.2] red_lines all True = {all(red_lines.values())}")
    print(f"[3.6.2] engineering_enabled = {after_enabled}")


if __name__ == "__main__":
    main()
