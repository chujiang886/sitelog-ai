"""Phase 3.9.14 —— Failure/Recovery/Rollback（Task 31）fail-closed 测试。"""

from __future__ import annotations

from agents.external_staging_runtime.failure_recovery import FailureRecoveryRollbackPlan
from agents.external_staging_runtime.identity import external_staging_identity


def test_production_rollback_forever_forbidden() -> None:
    rep = FailureRecoveryRollbackPlan(external_staging_identity()).build()
    assert rep.production_rollback_forbidden is True
    assert rep.passed is True


def test_local_fault_injection_and_recovery_permitted() -> None:
    rep = FailureRecoveryRollbackPlan(external_staging_identity()).build()
    # 本地合成故障注入 / 恢复模拟均为允许动作。
    assert rep.steps[0].permitted_by_scope is True
    assert rep.steps[1].permitted_by_scope is True
    assert rep.allowed_local_steps >= 2


def test_rollback_is_plan_only_not_executed() -> None:
    rep = FailureRecoveryRollbackPlan(external_staging_identity()).build()
    assert rep.steps[2].kind.value == "rollback_plan"
    assert rep.real_apply_allowed is False
    assert rep.is_production is False


def test_no_real_execution_invariants() -> None:
    rep = FailureRecoveryRollbackPlan(external_staging_identity()).build()
    assert rep.is_production is False
    assert rep.real_apply_allowed is False
