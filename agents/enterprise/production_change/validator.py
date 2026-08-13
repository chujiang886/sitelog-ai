"""Phase 3.9.7 企业生产变更管控平面 —— 门禁不变量校验（可被 CI / 脚本复用）。

本模块是 **fail-closed 守门器**：任何一项不通过，``check_change_control_invariants()``
返回 ``ok=False``。它校验的正是本层不可逾越的红线：

1. ``engineering_enabled`` 必须为 ``False``（全企业层 BUILT_NO_GO，红线①）；
2. 变更执行禁名（execute / deploy / rollback / apply / migrate / trigger_go …）必须存在于
   结构级禁名集，确保真实执行在结构上不可达（红线③/⑩）；
3. ``ChangeState`` 枚举不得包含 ``AUTO_EXECUTING`` / ``AUTO_COMPLETED`` / ``AI_APPROVED``
   等 AI 自动态（红线②/③/⑩）；
4. ``ChangeExecutionMode`` 不得包含 ``AI_AUTOMATIC``（红线③/⑩）；
5. 13 个 ``CHANGE_*`` 审计类目必须齐全（与 Ledger 一致）。
"""

from __future__ import annotations

from typing import Dict, List

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.production_change.forbidden import (
    PRODUCTION_CHANGE_FORBIDDEN_COUNT,
    _PRODUCTION_CHANGE_FORBIDDEN,
)
from agents.enterprise.production_change.models import (
    ChangeExecutionMode,
    ChangeState,
)
from agents.enterprise.red_line import safety_invariants_ok

# 13 个 CHANGE_* 审计类目（必须与 audit.py 枚举逐一对应，缺一则门禁失败）。
REQUIRED_CHANGE_CATEGORIES = {
    "CHANGE_REQUEST_CREATED",
    "CHANGE_PLAN_REGISTERED",
    "CHANGE_WINDOW_RESERVED",
    "CHANGE_PREFLIGHT_CHECKED",
    "CHANGE_CHECKPOINT_RECORDED",
    "CHANGE_ABORT_POLICY_REGISTERED",
    "CHANGE_ROLLBACK_REFERENCE_REGISTERED",
    "CHANGE_POST_VERIFICATION_REGISTERED",
    "CHANGE_EVIDENCE_SUBMITTED",
    "CHANGE_SIMULATION_PERFORMED",
    "CHANGE_FAILURE_SCENARIO_EVALUATED",
    "CHANGE_PACKAGE_GENERATED",
    "CHANGE_HUMAN_DECISION_RECORDED",
}

# 任何一条都必须存在于结构级禁名集（否则真实执行在结构上可达，门禁失败）。
REQUIRED_FORBIDDEN_METHODS = {
    "execute_change",
    "deploy_production",
    "rollback_production",
    "apply_change",
    "migrate_production",
    "trigger_go",
    "auto_execute_change",
    "auto_apply_change",
    "declare_change_go",
    "flip_engineering_for_change",
    "bypass_change_gate",
    "promote_simulation_to_production",
}

# 不得出现在 ChangeState / ChangeExecutionMode（AI 自动态一律禁止）。
FORBIDDEN_STATE_VALUES = {
    "auto_executing",
    "auto_completed",
    "ai_approved",
    "ai_automatic",
}


def check_change_control_invariants() -> Dict[str, object]:
    """返回门禁校验结果。``ok=False`` 表示任一红线不变量被破坏。"""

    findings: List[str] = []
    ok = True

    # 1) engineering_enabled 必须为 False
    if not safety_invariants_ok():
        ok = False
        findings.append(
            "safety_invariants_ok() == False：engineering_enabled 必须为 False（红线①）"
        )

    # 2) 结构级禁名集必须包含真实执行禁名
    forbidden_set = set(_PRODUCTION_CHANGE_FORBIDDEN)
    missing_forbidden = REQUIRED_FORBIDDEN_METHODS - forbidden_set
    if missing_forbidden:
        ok = False
        findings.append(
            f"结构级禁名集缺失真实执行禁名：{sorted(missing_forbidden)}（红线③/⑩）"
        )

    # 3) ChangeState 不得含 AI 自动态
    state_values = {s.value for s in ChangeState}
    bad_states = FORBIDDEN_STATE_VALUES & state_values
    if bad_states:
        ok = False
        findings.append(f"ChangeState 含禁止态：{sorted(bad_states)}（红线②/③/⑩）")

    # 4) ChangeExecutionMode 不得含 AI_AUTOMATIC
    mode_values = {m.value for m in ChangeExecutionMode}
    if "ai_automatic" in mode_values:
        ok = False
        findings.append("ChangeExecutionMode 含 ai_automatic（红线③/⑩）")

    # 5) 13 个 CHANGE_* 审计类目必须齐全
    cats = set(AuditActionCategory.__members__)
    missing_cats = REQUIRED_CHANGE_CATEGORIES - cats
    if missing_cats:
        ok = False
        findings.append(f"缺失 CHANGE_* 审计类目：{sorted(missing_cats)}")

    return {
        "ok": ok,
        "findings": findings,
        "forbidden_count": PRODUCTION_CHANGE_FORBIDDEN_COUNT,
        "required_forbidden_present": len(REQUIRED_FORBIDDEN_METHODS - missing_forbidden),
        "required_forbidden_total": len(REQUIRED_FORBIDDEN_METHODS),
        "category_count": len(AuditActionCategory),
        "required_categories_present": len(REQUIRED_CHANGE_CATEGORIES - missing_cats),
        "required_categories_total": len(REQUIRED_CHANGE_CATEGORIES),
    }


__all__ = ["check_change_control_invariants"]
