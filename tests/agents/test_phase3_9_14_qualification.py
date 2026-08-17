"""Phase 3.9.14 —— 13 项 Runtime Qualification fail-closed 测试（Task 20-28）。"""

from __future__ import annotations

from agents.external_staging_runtime.change_control import TERMINAL_STATE
from agents.external_staging_runtime.identity import external_staging_identity
from agents.external_staging_runtime.qualification import (
    QUALIFICATION_CHECKS,
    RuntimeQualificationHarness,
    RuntimeQualificationReport,
)


def _report() -> RuntimeQualificationReport:
    ident = external_staging_identity()
    return RuntimeQualificationHarness(ident).qualify_all()


def test_thirteen_checks_present() -> None:
    assert len(QUALIFICATION_CHECKS) == 13
    rep = _report()
    assert len(rep.checks) == 13


def test_all_checks_code_verified_structurally() -> None:
    rep = _report()
    assert rep.passed is True
    assert rep.code_verified_count == 13
    for c in rep.checks:
        assert c.code_verified is True
        assert c.status == "STRUCTURALLY_QUALIFIED_PENDING_RUNTIME"


def test_no_real_runtime_execution() -> None:
    rep = _report()
    assert rep.runtime_executed_count == 0
    assert all(c.runtime_executed is False for c in rep.checks)


def test_fail_closed_invariants() -> None:
    rep = _report()
    assert rep.is_production is False
    assert rep.real_apply_allowed is False
    ident = external_staging_identity()
    assert ident.kind.is_production is False


def test_data_policy_rejects_real_pii() -> None:
    # 负向：真实 PII / 生产快照必须被拒绝（结构性断言已被 harness 执行通过）。
    from agents.staging_runtime.data_policy import StagingDataPolicy

    pol = StagingDataPolicy(external_staging_identity())
    assert pol.classify("real_pii").permitted is False
    assert pol.classify("production_snapshot").permitted is False
    assert pol.classify("synthetic").permitted is True


def test_execution_scope_rejects_production_actions() -> None:
    from agents.staging_runtime.execution_scope import (
        FORBIDDEN_PRODUCTION_ACTIONS,
        StagingExecutionScope,
    )

    scope = StagingExecutionScope(external_staging_identity())
    assert all(not scope.is_permitted(a) for a in FORBIDDEN_PRODUCTION_ACTIONS)


def test_gate_check_emits_phase_3_9_14_terminal() -> None:
    # 资格第 13 项（gate_validation）必须产出 3.9.14 终端态。
    from agents.external_staging_runtime.change_control import StagingRuntimeValidationGate

    gate = StagingRuntimeValidationGate(external_staging_identity()).run()
    assert gate.terminal_state == TERMINAL_STATE
    assert gate.is_production is False
    assert gate.external_pending is True
