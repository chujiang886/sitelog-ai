"""Phase 3.9.14 —— 变更管控（Task 32）双钥匙/四角色/Apply Gate 4 态 fail-closed 测试。"""

from __future__ import annotations

import pytest

from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.external_staging_runtime.change_control import (
    TERMINAL_STATE,
    ApplyGateState,
    ChangeControlVerdict,
    DualKeyAuthorization,
    HumanAuthorizationKey,
    MachineSafetyKey,
    StagingRuntimeValidationGate,
    evaluate_change_control,
)
from agents.external_staging_runtime.identity import external_staging_identity


def test_gate_emits_3_9_14_terminal() -> None:
    v = StagingRuntimeValidationGate(external_staging_identity()).run()
    assert v.passed is True
    assert v.terminal_state == TERMINAL_STATE
    assert v.is_production is False
    assert v.external_pending is True
    assert v.human_verification_required is True


def test_no_authorization_is_pending() -> None:
    cc: ChangeControlVerdict = evaluate_change_control()
    assert cc.apply_gate_state is ApplyGateState.PENDING_HUMAN_AUTHORIZATION
    assert cc.dual_key_authorized is False
    assert cc.real_apply_allowed is False
    assert cc.is_production is False


def test_dual_key_requires_real_user_actor() -> None:
    # 双钥匙齐备（含真实 USER）才授权；仍非 GO/APPROVED，real_apply 仍禁止。
    mk = MachineSafetyKey(token="machine-safety-ok")
    hk = HumanAuthorizationKey(token="human-auth-ok", actor_kind="USER", actor="轩哥")
    auth = DualKeyAuthorization(machine_key=mk, human_key=hk)
    cc = evaluate_change_control(auth)
    assert cc.dual_key_authorized is True
    assert cc.apply_gate_state is ApplyGateState.AUTHORIZED_AWAITING_APPLY
    assert cc.real_apply_allowed is False
    assert cc.is_go_or_approved is False


def test_ai_cannot_mint_human_key() -> None:
    # AI 不得伪造 Human Authorization Key（actor_kind != USER 直接触发红线）。
    with pytest.raises(EnterpriseRedLineViolationError):
        HumanAuthorizationKey(token="fake", actor_kind="AI", actor="ai-agent")


def test_apply_gate_never_go_or_approved() -> None:
    # 4 态均不得等同于 GO / APPROVED / PRODUCTION_READY。
    for state in ApplyGateState:
        assert state.is_go_or_approved is False


def test_four_role_signoff_always_required() -> None:
    cc = evaluate_change_control()
    assert cc.four_role_signoff_required is True
    assert cc.human_actor_required is True
