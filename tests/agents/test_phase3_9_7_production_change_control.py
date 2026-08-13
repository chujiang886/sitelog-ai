"""Phase 3.9.7-change —— 生产变更管控平面 fail-closed 测试套件。

守 fail-closed 纪律（与 3.9.6 / 3.9.7 同源）：AI 永不宣称 GO / APPROVED / PRODUCTION_READY /
自动激活；任何 fail-closed 行为变更均不得用 skip / xfail 绕过至绿（红线⑧）。

覆盖：
- 真实执行类方法（execute_change / deploy_production / rollback_production / ...）结构不可达；
- 状态机无 AI 自动态（ChangeState 无 AUTO / APPROVED；ChangeExecutionMode 无 AI_AUTOMATIC）；
- 权限边界：真实 USER + 最小权限，AI / SYSTEM 一律 403，越权（跨权限）一律拒绝；
- 路由集：真实路由不含任何 absent_route（无 /execute /deploy /rollback /apply /migrate /activate）；
- 审计：13 个 CHANGE_* 类目齐全（审计总数 121）；
- 受控变更包 simulated_only 恒 True；受控仿真 is_simulation 恒 True（绝不执行真实变更）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.production_change.api_contract import (
    ABSENT_ROUTES,
    PRESENT_ROUTES,
)
from agents.enterprise.production_change.forbidden import _PRODUCTION_CHANGE_FORBIDDEN
from agents.enterprise.production_change.models import (
    ChangeExecutionMode,
    ChangeRequest,
    ChangeState,
)
from agents.enterprise.production_change.package import build_change_package
from agents.enterprise.production_change.permission_boundary import (
    ChangeOperation,
    ChangePermissionBoundaryError,
    require_change_operation,
)
from agents.enterprise.production_change.service import ProductionChangeControlService
from agents.enterprise.production_change.simulation import run_controlled_change_simulation
from agents.enterprise.production_change.validator import check_change_control_invariants
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from app.api.governance_change import router

#: 13 个 CHANGE_* 审计类目（value 字符串）。
CHANGE_CATEGORIES = [
    "change_request_created",
    "change_plan_registered",
    "change_window_reserved",
    "change_preflight_checked",
    "change_checkpoint_recorded",
    "change_abort_policy_registered",
    "change_rollback_reference_registered",
    "change_post_verification_registered",
    "change_evidence_submitted",
    "change_simulation_performed",
    "change_failure_scenario_evaluated",
    "change_package_generated",
    "change_human_decision_recorded",
]

#: 真实执行类禁名（结构不可达）。
RED_LINE_METHODS = [
    "execute_change",
    "deploy_production",
    "rollback_production",
    "apply_change",
    "migrate_production",
    "trigger_go",
    "auto_execute_change",
    "declare_change_go",
    "flip_engineering_for_change",
    "bypass_change_gate",
    "promote_simulation_to_production",
]


def _svc() -> ProductionChangeControlService:
    return ProductionChangeControlService(org_id="org-test", audit=AuditService(org_id="org-test"))


def test_red_line_methods_unreachable() -> None:
    svc = _svc()
    for name in RED_LINE_METHODS:
        assert name in _PRODUCTION_CHANGE_FORBIDDEN
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_state_machine_has_no_ai_auto_states() -> None:
    # 执行模式：仅 HUMAN_MANUAL / EXTERNAL_CONTROLLED_SYSTEM，无 AI_AUTOMATIC。
    assert "AI_AUTOMATIC" not in ChangeExecutionMode.__members__
    assert {m.name for m in ChangeExecutionMode} == {
        "HUMAN_MANUAL",
        "EXTERNAL_CONTROLLED_SYSTEM",
    }
    # 状态机：无 AUTO / APPROVED 类 AI 自动终态。
    assert all("AUTO" not in m for m in ChangeState.__members__)
    assert all("APPROVED" not in m for m in ChangeState.__members__)


def test_permission_boundary_user_read_ok() -> None:
    # 真实 USER + RELEASE_READ 可登记只读类操作（不抛异常）。
    require_change_operation(
        operation=ChangeOperation.RECORD_CHANGE_PLAN,
        actor_kind="user",
        granted_permissions=["governance:release:read"],
    )


def test_permission_boundary_ai_denied() -> None:
    # AI / SYSTEM 主体一律拒绝（红线③/⑥/⑧/⑨）。
    with pytest.raises(ChangePermissionBoundaryError):
        require_change_operation(
            operation=ChangeOperation.RECORD_CHANGE_PLAN,
            actor_kind="ai",
            granted_permissions=["governance:release:read"],
        )
    with pytest.raises(ChangePermissionBoundaryError):
        require_change_operation(
            operation=ChangeOperation.RECORD_CHANGE_PLAN,
            actor_kind="system",
            granted_permissions=["governance:release:read"],
        )


def test_permission_boundary_cross_org_signoff_denied() -> None:
    # 签署类操作需 RELEASE_SIGNOFF；仅持 RELEASE_READ 的真实 USER 仍被拒绝（职责分离）。
    with pytest.raises(ChangePermissionBoundaryError):
        require_change_operation(
            operation=ChangeOperation.REGISTER_CHANGE_SIGNOFF,
            actor_kind="user",
            granted_permissions=["governance:release:read"],
        )


def test_route_count_no_real_execution_endpoints() -> None:
    actual: set[str] = set()
    for r in router.routes:
        path = getattr(r, "path", "") or ""
        for m in getattr(r, "methods", None) or set():
            actual.add(f"{m.upper()} {path}")
    for absent in ABSENT_ROUTES:
        assert absent not in actual, f"real-execution endpoint present: {absent}"
    get_count = sum(1 for x in PRESENT_ROUTES if x["method"] == "GET")
    post_count = sum(1 for x in PRESENT_ROUTES if x["method"] == "POST")
    assert get_count == 13, f"expected 13 GET, got {get_count}"
    assert post_count == 13, f"expected 13 POST, got {post_count}"


def test_audit_change_categories_present() -> None:
    names = {c.name for c in AuditActionCategory}
    expected_names = {c.upper() for c in CHANGE_CATEGORIES}
    assert expected_names.issubset(names), (
        f"missing CHANGE categories: {expected_names - names}"
    )


def test_package_simulated_only() -> None:
    change = ChangeRequest(
        change_id="c1", title="t", description="d", requested_by="u1"
    )
    pkg = build_change_package(package_id="p1", change=change)
    assert pkg.simulated_only is True
    assert pkg.to_dict()["simulated_only"] is True
    # 变更请求永远不标 approved（fail-closed）。
    assert change.change_approved is False


def test_simulation_is_simulation_only() -> None:
    change = ChangeRequest(
        change_id="c1", title="t", description="d", requested_by="u1"
    )
    res = run_controlled_change_simulation(simulation_id="s1", change=change)
    assert res.is_simulation is True
    assert res.to_dict()["is_simulation"] is True


def test_change_control_invariants_ok() -> None:
    inv = check_change_control_invariants()
    assert inv["ok"] is True
    assert inv["category_count"] == 121
