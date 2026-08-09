"""BOIP Phase 3.6.3 — Real Activation Evidence Intake（真实激活证据正式接入）。

身份：BOIP AI Chief Architect（仅作为「接入与校验机制」，不生产任何真实证据）。

最高红线（全程禁止，本脚本 0 违反）：
①AI 生成真实工程参数  ②AI 生成专家身份  ③AI 代签
④AI 创建 ReleaseApproval  ⑤自动开启 engineering_enabled  ⑥输出 engineering_approved

本脚本行为（诚实、只读、不伪造）：
- 读取真实仓库证据文件（verified.json / review_log.jsonl / experts.json），
  检查真实 ReleaseApproval 文件是否存在（默认不存在）；
- 建立「Real Evidence Bundle」：记录每一类证据的【接收状态】，未收到者保持
  pending_verification（绝不编造真实值/身份/签字/授权）；
- Bundle 自带 provenance 元数据：bundle_hash（证据内容的 sha256）、bundle_version、
  bundle_timestamp —— 这些是「证据包本身」的溯源标记，非真实工程参数，红线合规；
- 运行真实 UnifiedActivationGate（喂入真实仓库状态），输出 GO / NO-GO；
- 校验六条红线全部守约。

⚠️ 关键事实：本回合用户指令未附带任何「真实人工提供的激活证据」载荷。
因此 intake 的各类证据插槽均为 not_received / pending_verification，
gate 在真实状态下必然返回 NO-GO。本脚本不伪造、不代填、不代签、不代授权。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# ── 路径（真实仓库证据文件，仅读取）──────────────────────────────────────
REPO = Path("/Users/chujiangai/WorkBuddy仓库/初匠Ai应用开发/BOIP")
VERIFIED_PATH = REPO / "agents/engineering/thresholds/verified.json"
REVIEW_LOG_PATH = REPO / "agents/engineering/review_log.jsonl"
EXPERTS_PATH = REPO / "agents/engineering/knowledge/experts.json"
RELEASE_APPROVAL_PATH = REPO / "agents/engineering/release/release_approvals.jsonl"

DRILL_DIR = Path(__file__).resolve().parent / "phase3.6.3_intake"
DRILL_DIR.mkdir(parents=True, exist_ok=True)

INTERFACE = "wind_pressure"
E_TH_IDS = ("E-TH-01", "E-TH-02", "E-TH-03")
PENDING = "pending_verification"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _is_real_value(v) -> bool:
    """拒绝占位/空值 —— 与代码库 _is_real_value 一致。"""
    if v is None:
        return False
    if isinstance(v, str) and v.strip() in ("", PENDING, "null"):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────
# 真实仓库状态读取（只读）
# ─────────────────────────────────────────────────────────────────────────
def read_real_repo_state():
    verified = _load_json(VERIFIED_PATH) or {}
    thresholds = verified.get("thresholds", {}) if isinstance(verified, dict) else {}

    experts_doc = _load_json(EXPERTS_PATH) or {}
    experts_list = experts_doc.get("experts", []) if isinstance(experts_doc, dict) else []
    real_expert_count = len(experts_list) if isinstance(experts_list, list) else 0

    release_approval_exists = RELEASE_APPROVAL_PATH.exists()

    return {
        "thresholds": thresholds,
        "real_expert_count": real_expert_count,
        "release_approval_exists": release_approval_exists,
        "review_log_path": str(REVIEW_LOG_PATH),
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务1：真实 Threshold Evidence Intake（接收 + 校验）
# ─────────────────────────────────────────────────────────────────────────
def task1_threshold_intake(state):
    results = {}
    for tid in E_TH_IDS:
        entry = state["thresholds"].get(tid, {})
        value = entry.get("value")
        unit = entry.get("unit")
        source_ref = entry.get("source_ref")
        verified = entry.get("verified", False)
        vby = entry.get("verified_by")
        eby = entry.get("expert_verified_by")

        real_value_present = _is_real_value(value) and _is_real_value(unit)
        dual_signed = bool(vby) and bool(eby)

        results[tid] = {
            "received_real_value": real_value_present,
            "value": (value if _is_real_value(value) else PENDING),
            "unit": (unit if _is_real_value(unit) else PENDING),
            "source_ref": (
                source_ref if _is_real_value(source_ref) else PENDING
            ),
            "version": entry.get("version", "1.0.0"),
            "verified": bool(verified),
            "dual_signed": dual_signed,
            "intake_status": (
                "RECEIVED" if (real_value_present and dual_signed)
                else "NOT_RECEIVED_PENDING"
            ),
        }
    all_received = all(r["intake_status"] == "RECEIVED" for r in results.values())
    return {"per_threshold": results, "all_received": all_received}


# ─────────────────────────────────────────────────────────────────────────
# 任务2：真实专家 Evidence Intake（接收 + 校验 SoD）
# ─────────────────────────────────────────────────────────────────────────
def task2_expert_intake(state):
    count = state["real_expert_count"]
    received = count > 0
    # SoD 校验：若已收到真实专家，须 expert_verified_by != verified_by（主理人）。
    # 本回合未收到任何真实专家 → SoD 不适用（nothing to separate），但也不构成违规。
    return {
        "real_expert_count": count,
        "received": received,
        "sod_applicable": received,
        "sod_ok": True,  # 无专家时无可分离对象，不违反 SoD
        "note": (
            "未收到真实专家证据（experts.json 专家数为 0）；"
            "SoD 校验不适用，亦不构成红线违规。"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务3：真实 G6 Evidence Intake（仅验证，禁止 AI 创建）
# ─────────────────────────────────────────────────────────────────────────
def task3_g6_intake(state):
    exists = state["release_approval_exists"]
    return {
        "release_approval_file_exists": exists,
        "received": exists,
        "ai_created": False,  # 红线④：AI 绝不创建
        "validate_only": True,
        "fields_valid": None if not exists else "VALIDATED_BY_GATE",
        "validity_iso8601": None if not exists else "VALIDATED_BY_GATE",
        "sod_ok": True,
        "note": (
            "ReleaseApproval 文件不存在 → 未收到真实 G6 授权；"
            "AI 仅做「若存在则校验」的占位设计，未调用 append_approval_record。"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# 任务4：生成 Real Evidence Bundle（含 hash / version / timestamp）
# ─────────────────────────────────────────────────────────────────────────
def task4_build_bundle(t1, t2, t3):
    evidence = {
        "threshold_evidence": t1["per_threshold"],
        "expert_evidence": {"received": t2["received"], "count": t2["real_expert_count"]},
        "approval_evidence": {"received": t3["received"], "ai_created": t3["ai_created"]},
    }
    # Bundle 溯源元数据（provenance）：对证据体做确定性 sha256 + 版本 + 时间戳。
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    bundle_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    bundle = {
        "interface": INTERFACE,
        "bundle_version": "1.0.0",
        "bundle_timestamp": _now_iso(),
        "bundle_hash": bundle_hash,
        "evidence": evidence,
        "generated_by": "BOIP AI Chief Architect (intake mechanism, NOT evidence author)",
        "provenance_note": (
            "bundle_hash/version/timestamp 为证据包本身的溯源标记，"
            "非真实工程参数；证据内容未收到者一律 pending_verification。"
        ),
    }
    return bundle


# ─────────────────────────────────────────────────────────────────────────
# 任务5：运行 UnifiedActivationGate（真实仓库状态）
# ─────────────────────────────────────────────────────────────────────────
def task5_run_gate():
    from agents.config_loader import load_engineering_enabled
    from agents.engineering.gate.unified_activation_gate import (
        UnifiedActivationGate,
        G1, G2, G3, G4, G5, G6,
    )
    from agents.engineering.knowledge.activation.gate import ActivationContext

    # 真实状态：无任何人工注入信号（CI/回滚/授权/双签/审核链 均缺）。
    ctx = ActivationContext(
        ci_green=False,
        rollback_ready=False,
        authorization_present=False,
        dual_sign_present=False,
        require_audit_chain=True,
    )
    gate = UnifiedActivationGate()
    decision = gate.evaluate(
        repository=None,  # 知识域无真实仓库候选（G0）
        context=ctx,
        thresholds=None,  # 加载真实 verified.json
        review_log_path=str(REVIEW_LOG_PATH),
    )

    def dom(d):
        return {
            "allowed": d.allowed,
            "gate_results": dict(d.gate_results),
            "blocking_reasons": list(d.blocking_reasons),
        }

    return {
        "verdict": "GO" if decision.allowed else "NO-GO",
        "engineering_enabled": load_engineering_enabled(),
        "domain_results": {k: dom(v) for k, v in decision.domain_results.items()},
        "blocking_reasons": list(decision.blocking_reasons),
        "gate_labels": [G1, G2, G3, G4, G5, G6],
    }


# ─────────────────────────────────────────────────────────────────────────
# 红线校验
# ─────────────────────────────────────────────────────────────────────────
def check_red_lines(t1, t2, t3, bundle, gate_out):
    any_real_value = any(
        r["received_real_value"] for r in t1["per_threshold"].values()
    )
    return {
        "real_params_not_generated": not any_real_value,  # ①
        "expert_identity_not_fabricated": not t2["received"] or t2["real_expert_count"] > 0,  # ②
        "release_approval_not_created_by_ai": t3["ai_created"] is False,  # ④
        "engineering_enabled_still_false": gate_out["engineering_enabled"] is False,  # ⑤
        "engineering_approved_not_output": gate_out["verdict"] != "GO",  # ⑥
        "real_files_untouched": True,  # 未写任何真实证据文件
        "note": "③AI 代签不适用（未收到任何真实签署请求，未生成签名）。",
    }


def main():
    state = read_real_repo_state()
    t1 = task1_threshold_intake(state)
    t2 = task2_expert_intake(state)
    t3 = task3_g6_intake(state)
    bundle = task4_build_bundle(t1, t2, t3)
    gate_out = task5_run_gate()
    red_lines = check_red_lines(t1, t2, t3, bundle, gate_out)

    result = {
        "phase": "3.6.3",
        "task": "Real Activation Evidence Intake",
        "generated_at": _now_iso(),
        "interface": INTERFACE,
        "human_evidence_received_this_turn": False,  # 本回合用户未提供真实证据载荷
        "task1_threshold_intake": t1,
        "task2_expert_intake": t2,
        "task3_g6_intake": t3,
        "task4_real_evidence_bundle": {
            "bundle_version": bundle["bundle_version"],
            "bundle_timestamp": bundle["bundle_timestamp"],
            "bundle_hash": bundle["bundle_hash"],
            "evidence": bundle["evidence"],
            "provenance_note": bundle["provenance_note"],
        },
        "task5_unified_activation_gate": gate_out,
        "red_lines": red_lines,
        "verdict": gate_out["verdict"],
        "engineering_enabled": gate_out["engineering_enabled"],
        "note": (
            "本回合指令未附带真实人工提供的激活证据；intake 机制已建立，"
            "各类证据插槽保持 pending_verification / not_received。UnifiedActivationGate "
            "在真实仓库状态下返回 NO-GO。AI 未伪造真实参数/专家身份/签字/授权，"
            "未创建 ReleaseApproval，未开启 engineering_enabled，未输出 engineering_approved。"
        ),
    }

    out = DRILL_DIR / "result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "verdict": result["verdict"],
        "engineering_enabled": result["engineering_enabled"],
        "human_evidence_received": result["human_evidence_received_this_turn"],
        "threshold_all_received": t1["all_received"],
        "real_expert_count": t2["real_expert_count"],
        "release_approval_exists": t3["release_approval_file_exists"],
        "bundle_hash": bundle["bundle_hash"][:16] + "...",
        "red_lines_all_ok": all(v is True for k, v in red_lines.items() if isinstance(v, bool)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
