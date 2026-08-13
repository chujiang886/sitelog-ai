"""Phase 3.9.8 T16 —— 生产激活干跑与人工决策演练 全套模拟测试（agents 层）。

重点断言（fail-closed）：
  - 干跑报告的红线恒 intact（engineering_enabled/production_activated False、real_signoff_count 0）；
  - 干跑绝不产生污染信号（contamination.detected is False）；
  - 负路径矩阵全部 rejected（fail-closed 拒绝越权/污染输入）；
  - 决策场景矩阵 = 14 条；
  - 模拟命名空间一旦 simulation_only=False 立即拒绝构造（红线⑩）；
  - 真实生产控制平面类型（HumanSignoffRegistry）一旦进入模拟层即被污染守卫拒绝
    （红线③/④/⑧/⑩：模拟数据绝不进入真实 registry）；
  - 干跑产生的审计记录全部为 simulation-only（actor_kind 恒 AI、detail 强制红线标记、
    类别全在 Phase 3.9.8 八类 simulation-only 枚举内），绝不登记真实 human signoff / real decision。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.production_release.human_signoff import HumanSignoffRegistry
from agents.enterprise.production_release.simulation import (
    ProductionActivationNegativePathMatrix,
    ProductionActivationSimulationContext,
    SimulationContaminationError,
    SimulationError,
    build_decision_scenario_matrix,
    build_simulation_context,
    run_production_activation_dry_run,
)

# Phase 3.9.8 八类 simulation-only 审计动作（与 agents/enterprise/audit.py 对齐，121 → 129）。
SIMULATION_ONLY_CATEGORIES = {
    "production_activation_dry_run_started",
    "production_activation_dry_run_completed",
    "production_activation_simulation_decision_evaluated",
    "production_activation_simulation_evidence_built",
    "production_activation_simulation_signoff_built",
    "production_activation_handoff_dry_run",
    "production_activation_abort_simulated",
    "production_activation_rollback_simulated",
}

ALLOWED_REPORT_STATUS = {"simulation_pass", "simulation_blocked"}
RED_LINE_MARKER = "engineering_enabled=false;production_activated=false"


# --------------------------------------------------------------------------- #
# 干跑红线
# --------------------------------------------------------------------------- #


def test_dry_run_red_lines_intact() -> None:
    audit = AuditService(org_id="simulation")
    report = run_production_activation_dry_run(
        simulation_id="test-red-lines",
        candidate_id="RC-3.9.8-SIM",
        scenario="production_activation_full_dry_run",
        audit=audit,
    )
    assert report.production_activated is False
    assert report.real_signoff_count == 0
    assert report.engineering_enabled is False
    assert report.status.value in ALLOWED_REPORT_STATUS


def test_dry_run_contamination_clean() -> None:
    audit = AuditService(org_id="simulation")
    report = run_production_activation_dry_run(
        simulation_id="test-contamination",
        candidate_id="RC-3.9.8-SIM",
        scenario="production_activation_full_dry_run",
        audit=audit,
    )
    payload = report.to_dict()
    contamination = payload.get("contamination", {})
    assert contamination.get("detected") is not True, f"干跑产生污染信号：{contamination}"


# --------------------------------------------------------------------------- #
# 负路径 / 场景矩阵
# --------------------------------------------------------------------------- #


def test_negative_paths_all_rejected() -> None:
    ctx = build_simulation_context(
        simulation_id="test-negative",
        candidate_id="RC-3.9.8-SIM",
        scenario="negative-paths",
    )
    results = ProductionActivationNegativePathMatrix().evaluate(context=ctx)
    assert len(results) >= 10, f"负路径数量不足（应 ≥10）：{len(results)}"
    unguarded = [n.path_id for n in results if not (n.expected_reject and n.rejected)]
    assert not unguarded, f"存在未被 fail-closed 拒绝的负路径：{unguarded}"


def test_scenario_matrix_count_14() -> None:
    scenarios = build_decision_scenario_matrix()
    assert len(scenarios) == 14, f"决策场景数量异常（应=14）：{len(scenarios)}"


# --------------------------------------------------------------------------- #
# 模拟命名空间 / 污染守卫（红线⑩）
# --------------------------------------------------------------------------- #


def test_simulation_context_rejects_non_simulation() -> None:
    with pytest.raises(SimulationError):
        ProductionActivationSimulationContext(
            simulation_id="x",
            candidate_id="RC-3.9.8-SIM",
            scenario="y",
            started_at="2026-08-13T00:00:00Z",
            simulation_only=False,  # 红线⑩：模拟对象不得伪装成真实对象
            engineering_enabled_at_start=False,
        )


def test_no_real_registry_contamination_guard() -> None:
    # 真实生产控制平面类型一旦进入模拟层即被拒绝。
    real_registry = HumanSignoffRegistry(rc_id="real-rc")
    with pytest.raises(SimulationContaminationError):
        ProductionActivationNegativePathMatrix._assert_no_real_production_object(
            real_registry
        )

    # 非真实类型不应触发守卫（避免误杀合法合成对象）。
    ProductionActivationNegativePathMatrix._assert_no_real_production_object(object())


# --------------------------------------------------------------------------- #
# 干跑审计记录全为 simulation-only（红线③/④/⑧/⑩）
# --------------------------------------------------------------------------- #


def test_dry_run_audit_records_simulation_only() -> None:
    audit = AuditService(org_id="simulation")
    run_production_activation_dry_run(
        simulation_id="test-audit-records",
        candidate_id="RC-3.9.8-SIM",
        scenario="production_activation_full_dry_run",
        audit=audit,
    )
    records = audit._records
    assert records, "干跑未产生任何审计记录（异常）"

    for rec in records:
        # actor_kind 恒 AI（干跑由 AI 驱动，非人工责任节点）。
        assert rec.actor_kind == AuditActorKind.AI, (
            f"模拟审计记录 actor_kind 非 AI：{rec.actor_kind}"
        )
        # detail 强制携带红线标记。
        assert RED_LINE_MARKER in (rec.detail or ""), (
            f"模拟审计记录 detail 缺失红线标记：{rec.detail}"
        )
        # 类别全在 Phase 3.9.8 simulation-only 八类内，绝不登记真实 human signoff / real decision。
        assert rec.category in SIMULATION_ONLY_CATEGORIES, (
            f"干跑产生了非 simulation-only 审计类别（污染真实命名空间）：{rec.category}"
        )
