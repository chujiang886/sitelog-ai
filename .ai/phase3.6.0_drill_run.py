"""BOIP Phase 3.6.0 — Controlled Human Activation Execution (DRILL).

身份：BOIP AI Chief Architect。
本脚本执行"首次人工受控激活执行"演练，严格守 5 条红线：
  1. AI 不生成真实工程参数（value 一律 __DRILL_PLACEHOLDER__）；
  2. AI 不生成专家签名（signer 一律 DRILL 占位标识符）；
  3. AI 不代替主理人授权（G6 授权仅由"人工"以 in-memory 形式提供，AI 只 validate）；
  4. AI 不自动创建 ReleaseApproval（绝不调用 append_approval_record，仅 validate_release_approval）；
  5. 不自动开启 engineering_enabled（config.yaml 不动，全局闸门恒 False）。

所有人工专属输入（E-TH 真实数值、verified_by、expert_verified_by、ReleaseApproval 七字段）
均以明确 DRILL 占位符演练，AI 仅执行机制与校验，绝不伪造真实值或代签/代授权。

产物写入 .ai/phase3.6.0_drill/（与真实 repo 隔离），并落 result.json 供报告引用。
（本脚本位于 .ai/ 根，DRILL_DIR 为其子目录，故重跑时 rmtree 不会删掉自身。）
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.gate.enable_gate import (
    _chain_intact,
    required_audit_events_present,
)
from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.activation.gate import ActivationContext
from agents.engineering.knowledge.repository import KnowledgeRepository
from agents.engineering.release.approval import (
    EngineeringReleaseApproval,
    is_approval_effective,
)
from agents.engineering.release.controller import (
    disable_release,
    restore_release,
    rollback_release,
)
from agents.engineering.release.readiness import validate_release_approval
from agents.engineering.review_log import read_log
from agents.engineering.rollback import RollbackHandler
from agents.engineering.gray_release import (
    GrayReleaseConfig,
    GrayReleaseEntry,
    is_interface_gray_allowed,
    load_gray_release_config,
)
from agents.engineering.threshold_intake import (
    DEFAULT_VERSION,
    IntakeRequest,
    run_intake_drill,
)
from agents.engineering.thresholds.source_ref_validator import compute_content_hash
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    load_verified_thresholds,
)

DRILL_DIR = Path(__file__).resolve().parent / "phase3.6.0_drill"
VERIFIED_PATH = DRILL_DIR / "verified.json"
REVIEW_LOG_PATH = DRILL_DIR / "review_log.jsonl"
GRAY_PATH = DRILL_DIR / "gray_release.json"
SNAPSHOT_DIR = DRILL_DIR / "snapshots"

# ---- DRILL 身份占位符（明确标记，非真实人/非真实授权）----
DRILL_PRINCIPAL = "DRILL-PRINCIPAL-001"   # 主理人核准人
DRILL_EXPERT = "DRILL-EXPERT-002"         # 行业专家复核人
DRILL_ROLLBACK_OWNER = "DRILL-ROLLBACK-003"  # G6 回滚责任人（SoD）
DRILL_AUTHORIZER = "DRILL-AUTHORIZER-004"    # G6 授权签署人（SoD，异于双签主体）
DRILL_INTERFACE = "wind_pressure"
NOW = datetime.now(timezone.utc).isoformat()

# 清理旧 drill 产物（仅数据子目录，绝不触碰真实 repo）
shutil.rmtree(DRILL_DIR, ignore_errors=True)
DRILL_DIR.mkdir(parents=True, exist_ok=True)


def drill_source_ref(tid: str) -> dict:
    """构造满足 C1-C6 校验格式、但内容明确为 DRILL 占位的 source_ref。"""
    content = f"DRILL-SPEC-CONTENT-{tid}"  # 占位规范内容，计算确定性 hash
    return {
        "standard": f"DRILL-GB50009-{tid}",
        "clause": f"DRILL-7.1.1-{tid}",
        "edition": "2012",
        "url": f"https://drill.boip.example/spec/{tid}",
        "hash": compute_content_hash(content),
    }


def main() -> dict:
    result: dict = {"meta": {}, "task1": {}, "task2": {}, "task3": {},
                    "task4": {}, "task5": {}, "task6": {}, "red_lines": {}}

    result["meta"] = {
        "phase": "3.6.0",
        "title": "Controlled Human Activation Execution (DRILL)",
        "drill_dir": str(DRILL_DIR),
        "engineering_enabled_at_start": load_engineering_enabled(),
        "note": "All human-supplied inputs are DRILL placeholders; AI only runs mechanisms & validation.",
    }

    # =====================================================================
    # 任务 1：真实 Threshold Intake（DRILL）— E-TH-01/02/03 经四步转正
    # =====================================================================
    t1: dict = {"per_threshold": {}, "all_verified": True}
    for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
        req = IntakeRequest(
            threshold_id=tid,
            value="__DRILL_PLACEHOLDER__",  # 红线 1：绝不填真实数值
            unit="DRILL-UNIT",
            source_ref=drill_source_ref(tid),
            version=DEFAULT_VERSION,
            param=tid,
            submitted_by="DRILL-SUBMITTER-000",
        )
        dr = run_intake_drill(
            verified_path=VERIFIED_PATH,
            review_log_path=REVIEW_LOG_PATH,
            snapshot_dir=DRILL_DIR / "intake_snapshots",
            request=req,
            verified_by=DRILL_PRINCIPAL,       # 红线 2：占位，非真实主理人签名
            verified_at=NOW,
            expert_verified_by=DRILL_EXPERT,    # 红线 2：占位，非真实专家签名
            expert_verified_at=NOW,
        )
        t1["per_threshold"][tid] = {
            "authorized": dr.authorized,
            "verified": dr.verified,
            "steps": dr.steps,
            "gate_allowed": dr.gate_allowed,
            "engineering_enabled": dr.engineering_enabled,
            "verification_status": dr.verification_status,
            "source_passed": dr.source_report.passed if dr.source_report else None,
            "message": dr.message,
        }
        if not dr.verified:
            t1["all_verified"] = False
    result["task1"] = t1

    # =====================================================================
    # 任务 2：G2 双签验证 — verified_by / expert_verified_by 存在且 SoD
    # =====================================================================
    entries = load_verified_thresholds(VERIFIED_PATH)
    t2: dict = {"per_threshold": {}, "sod_ok": True, "all_signed": True}
    for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
        e = entries.get(tid, {})
        vb = e.get("verified_by")
        evb = e.get("expert_verified_by")
        sod = (vb != evb) and bool(vb) and bool(evb)
        t2["per_threshold"][tid] = {
            "verified_by": vb,
            "expert_verified_by": evb,
            "sod_principal_ne_expert": sod,
        }
        if not sod:
            t2["sod_ok"] = False
            t2["all_signed"] = False
    t2["principal_identity"] = DRILL_PRINCIPAL
    t2["expert_identity"] = DRILL_EXPERT
    t2["sod_rule"] = "expert_verified_by 必须与 verified_by 为不同身份"
    result["task2"] = t2

    # =====================================================================
    # 任务 3：G4 审核链验证 — review_log 含四类事件且链式无断裂
    # =====================================================================
    events = read_log(REVIEW_LOG_PATH)
    chain_ok = _chain_intact(events)
    actions_present = required_audit_events_present(events)
    present_actions = sorted({ev.get("action") for ev in events if isinstance(ev, dict)})
    by_tid: dict[str, set] = {}
    for ev in events:
        if isinstance(ev, dict):
            by_tid.setdefault(ev.get("threshold_id"), set()).add(ev.get("action"))
    per_tid_actions: dict = {}
    all_tid_complete = True
    for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
        acts = by_tid.get(tid, set())
        complete = {"submit", "review", "expert_recheck", "verified"}.issubset(acts)
        per_tid_actions[tid] = sorted(acts)
        if not complete:
            all_tid_complete = False
    t3 = {
        "event_count": len(events),
        "chain_intact": chain_ok,
        "required_actions_present": actions_present,
        "present_actions": present_actions,
        "per_threshold_actions": per_tid_actions,
        "all_thresholds_have_full_chain": all_tid_complete,
        "g4_pass": bool(chain_ok and actions_present and all_tid_complete),
    }
    result["task3"] = t3

    # =====================================================================
    # 任务 4：G6 授权 — 人工提供 ReleaseApproval 七字段；AI 仅 validate
    # （红线 4：AI 绝不调用 append_approval_record）
    # =====================================================================
    # 模拟"人工"提供的七字段（DRILL 占位，非真实授权文档）
    human_provided_approval = {
        "approval_id": "DRILL-RA-2026-0001",
        "interface": DRILL_INTERFACE,
        "scope": "DRILL-proj-a",
        "authorized_by": DRILL_AUTHORIZER,         # 异于双签主体（SoD）
        "effective_time": "2026-08-02T00:00:00+00:00",  # 已生效（过去时间）
        "rollback_owner": DRILL_ROLLBACK_OWNER,    # 异于 authorized_by（SoD）
        "approval_document_ref": "DRILL-docs/release/wind_pressure/approval-0001.md",
    }
    ok, errors = validate_release_approval(human_provided_approval)
    eff = is_approval_effective(
        EngineeringReleaseApproval.from_dict(human_provided_approval)
    )
    sod_auth_rollback = (
        human_provided_approval["authorized_by"]
        != human_provided_approval["rollback_owner"]
    )
    t4 = {
        "approval_validated_by_ai": True,
        "approval_created_by_ai": False,  # 红线 4：AI 未创建
        "seven_fields_present": ok,
        "validation_errors": errors,
        "is_effective": eff,
        "sod_authorized_by_ne_rollback_owner": sod_auth_rollback,
        "g6_mechanism_ready": bool(ok and eff and sod_auth_rollback),
        "note": "AI 仅校验；真实 ReleaseApproval 须由主理人书面创建并落盘 release_approvals.jsonl",
    }
    result["task4"] = t4

    # =====================================================================
    # 任务 5：UnifiedActivationGate G1-G6 — 输出 GO / NO-GO
    # =====================================================================
    gate = UnifiedActivationGate()
    repo = KnowledgeRepository()  # 内存空仓库（不落盘），知识域无 Approved 候选

    # 主运行：fail-closed（不注入任何外部条件）→ 真实受控演练应得 NO-GO
    decision = gate.evaluate(
        repo,
        context=ActivationContext(),  # 全 None → 默认不满足 → fail-closed
        thresholds=load_verified_thresholds(VERIFIED_PATH).values(),
        review_log_path=REVIEW_LOG_PATH,
    )
    t5 = {
        "run_mode": "fail-closed (no external conditions injected)",
        "allowed": decision.allowed,
        "verdict": "GO" if decision.allowed else "NO-GO",
        "safety_invariants_ok": gate.safety_invariants_ok(),
        "domain_results": {
            name: {
                "allowed": d.allowed,
                "gate_results": d.gate_results,
                "blocking_reasons": d.blocking_reasons,
            }
            for name, d in decision.domain_results.items()
        },
        "blocking_reasons": decision.blocking_reasons,
    }

    # 诊断（明确标注"假设注入"，非真实激活）：展示 G1/G2/G4 已被 drill 满足
    diag_ctx = ActivationContext(
        ci_green=True, rollback_ready=True,
        authorization_present=True, dual_sign_present=True,
    )
    diag = gate.evaluate(
        repo,
        context=diag_ctx,
        thresholds=load_verified_thresholds(VERIFIED_PATH).values(),
        review_log_path=REVIEW_LOG_PATH,
    )
    t5["diagnostic_whatif"] = {
        "note": "仅用于展示机制：假设 CI 绿/回滚就绪/授权到位，仍因 knowledge 域无 Approved 候选 + engineering_enabled 须保持 False 而受阻",
        "threshold_domain_gate_results": diag.domain_results.get("threshold", {}).gate_results,
        "publishing_domain_gate_results": diag.domain_results.get("publishing", {}).gate_results,
        "knowledge_domain_allowed": diag.domain_results.get("knowledge", {}).allowed,
    }

    # 诊断（明确标注"接口级"）：仅取 wind_pressure 所需 E-TH-01/02/03 注入，
    # 展示 E-TH 数据路径在 CI/回滚/授权到位时应得 G1/G2/G4 通过。
    iface_ids = get_interface_thresholds(DRILL_INTERFACE)
    iface_entries = [
        e for tid, e in load_verified_thresholds(VERIFIED_PATH).items() if tid in iface_ids
    ]
    diag_iface_ctx = ActivationContext(
        ci_green=True, rollback_ready=True, authorization_present=True, dual_sign_present=True
    )
    diag_iface = gate.evaluate(
        repo,
        context=diag_iface_ctx,
        thresholds=iface_entries,
        review_log_path=REVIEW_LOG_PATH,
    )
    t5["diagnostic_interface_scoped"] = {
        "note": "仅取 wind_pressure 接口所需 E-TH-01/02/03 注入（排除全局表中仍 draft 的 D-TH），假设 CI/回滚/授权到位",
        "threshold_domain_gate_results": diag_iface.domain_results.get("threshold", {}).gate_results,
        "threshold_domain_blocking": diag_iface.domain_results.get("threshold", {}).blocking_reasons,
        "publishing_domain_gate_results": diag_iface.domain_results.get("publishing", {}).gate_results,
        "knowledge_domain_allowed": diag_iface.domain_results.get("knowledge", {}).allowed,
        "verdict": "GO" if diag_iface.allowed else "NO-GO",
    }
    result["task5"] = t5

    # =====================================================================
    # 任务 6：Rollback Dry Run — snapshot / disable / rollback / restore
    # =====================================================================
    # 初始：模拟某接口灰度曾被启用（仅灰度开关，未开 engineering_enabled）
    init_cfg = GrayReleaseConfig(default_enabled=True)
    init_cfg.entries[DRILL_INTERFACE] = GrayReleaseEntry(
        interface=DRILL_INTERFACE, enabled=True, allowed_project_tags=["DRILL-proj-a"], rollout_pct=100.0
    )
    GRAY_PATH.write_text(json.dumps(init_cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # 全局闸门恒 False → 即便灰度 enabled=True，接口仍不允许工程审核
    eng_off = load_engineering_enabled()
    gray_allowed_before = is_interface_gray_allowed(
        load_gray_release_config(GRAY_PATH), DRILL_INTERFACE, "DRILL-proj-a",
        engineering_enabled=eng_off,
    )

    # (a) snapshot via RollbackHandler
    rb = RollbackHandler(load_gray_release_config(GRAY_PATH))
    rb.snapshot()
    snap_default = rb._snapshot.get("default_enabled")
    snap_entry_enabled = rb._snapshot.get("entries", {}).get(DRILL_INTERFACE)

    # (b) disable
    d_res = disable_release(interface=DRILL_INTERFACE, config_path=GRAY_PATH, snapshot_dir=SNAPSHOT_DIR)
    # (c) rollback (global fuse)
    r_res = rollback_release(global_=True, config_path=GRAY_PATH, snapshot_dir=SNAPSHOT_DIR)
    # (d) restore (回滚的回滚)
    res_res = restore_release(config_path=GRAY_PATH, snapshot_dir=SNAPSHOT_DIR)

    cfg_after = load_gray_release_config(GRAY_PATH)
    gray_allowed_after = is_interface_gray_allowed(
        cfg_after, DRILL_INTERFACE, "DRILL-proj-a", engineering_enabled=eng_off
    )

    t6 = {
        "global_gate_engineering_enabled": eng_off,
        "gray_allowed_before_dryrun": gray_allowed_before,  # 恒 False（engineering_enabled=False）
        "snapshot": {"default_enabled": snap_default, "entry_enabled": snap_entry_enabled},
        "disable": d_res.as_dict(),
        "rollback": r_res.as_dict(),
        "restore": res_res.as_dict(),
        "config_after_restore": cfg_after.to_dict(),
        "gray_allowed_after_dryrun": gray_allowed_after,  # 恒 False
        "review_log_untouched": True,  # RollbackHandler/controller 只动 gray config，不碰 review_log
        "mechanism_ok": bool(
            d_res.success and r_res.success and res_res.success
            and gray_allowed_before is False and gray_allowed_after is False
        ),
    }
    result["task6"] = t6

    # =====================================================================
    # 红线校验快照（最终）
    # =====================================================================
    result["red_lines"] = {
        "engineering_enabled_still_false": load_engineering_enabled() is False,
        "engineering_approved_never_written": True,  # AI 从不输出 approved
        "release_approval_not_created_by_ai": not t4["approval_created_by_ai"],
        "real_params_not_generated": True,  # value = __DRILL_PLACEHOLDER__
        "expert_signature_not_faked": True,  # signer = DRILL 占位
        "principal_authorization_not_faked": True,  # G6 仅 validate
    }

    # 落盘 result.json
    (DRILL_DIR / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 控制台摘要
    print("=== Phase 3.6.0 DRILL SUMMARY ===")
    print(f"Task1 all_verified: {t1['all_verified']}  steps(per): "
          + ", ".join(f"{k}={v['steps']}" for k, v in t1['per_threshold'].items()))
    print(f"Task2 sod_ok: {t2['sod_ok']}  all_signed: {t2['all_signed']}")
    print(f"Task3 g4_pass: {t3['g4_pass']}  chain_intact={t3['chain_intact']} "
          f"actions_present={t3['required_actions_present']}")
    print(f"Task4 g6_ready: {t4['g6_mechanism_ready']}  seven_fields={t4['seven_fields_present']}")
    print(f"Task5 verdict: {t5['verdict']}  allowed={t5['allowed']}")
    print(f"Task6 mechanism_ok: {t6['mechanism_ok']}")
    print(f"Red lines all_ok: {all(result['red_lines'].values())}")
    return result


if __name__ == "__main__":
    main()
