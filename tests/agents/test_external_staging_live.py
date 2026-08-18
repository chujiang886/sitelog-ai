"""Phase 3.9.15 External Staging Real Resource Live Qualification — fail-closed tests.

Tests the SOFTWARE guarantees actually committed in this branch:

- The terminal state is BUILT_NO_GO and contains no forbidden GO/APPROVED/PRODUCTION_READY.
- The 8-resource aggregator honestly reports 0/8 by default (no forgery).
- The 8-resource state machine rejects illegal jumps and requires the full adjacent path.
- Dual-key authorization: AI cannot mint a Human Authorization Key; staging apply is never
  a GO; production apply is BLOCKED.
- The deterministic package hash is reproducible and passes the fail-closed validator, and
  an 8/8 claim without real deploy + real E2E evidence is rejected (anti-fabrication).
- NEW 3.9.15 provider-acquisition capability: init classification, acquisition feasibility,
  and report flags (real_apply_allowed is ALWAYS False; no forged init/validate/plan PASS).

No real provisioning, credential, or production action is performed by these tests.

NOTE: isolation / runtime-live / provider-account / deployment *state* classes already live
in the reused 3.9.14 ``staging_runtime`` core; this branch does NOT re-implement them, so
they are intentionally not imported here.
"""

from __future__ import annotations

import re

import pytest

from agents.external_staging_live import (
    ALL_RESOURCES,
    LIVE_TERMINAL_STATE,
    DualKeyAuthorization,
    ExternalStagingResource,
    HumanAuthorizationKey,
    IllegalStateTransitionError,
    MachineSafetyKey,
    PartialAggregator,
    ResourceLiveState,
    ResourceLiveStateMachine,
    build_live_package,
    evaluate_live_apply_gate,
    validate_package,
)
from agents.external_staging_live.change_control import EnterpriseRedLineViolationError
from agents.external_staging_live.provider_acquisition import (
    ProviderAcquisitionReport,
    ProviderInitClassification,
    assess_acquisition_feasibility,
    build_report,
    classify_init,
)


# --- terminal state ----------------------------------------------------------
def test_terminal_state_is_built_no_go_and_legal():
    assert LIVE_TERMINAL_STATE == (
        "PHASE_3_9_15_EXTERNAL_STAGING_REAL_RESOURCE_LIVE_QUALIFICATION_BUILT_NO_GO"
    )
    assert "APPROVED" not in LIVE_TERMINAL_STATE
    assert "PRODUCTION_READY" not in LIVE_TERMINAL_STATE
    assert not re.search(r"(?<!_)GO(?!_)", LIVE_TERMINAL_STATE)


# --- aggregator honesty ------------------------------------------------------
def test_aggregator_defaults_to_zero_of_eight():
    agg = PartialAggregator()
    assert agg.total() == 8
    assert agg.qualified_count() == 0
    assert agg.verdict() == "NOT_QUALIFIED"
    assert set(agg.snapshot().keys()) == {r.value for r in ALL_RESOURCES}
    assert all(v == "PENDING_EXTERNAL_STAGING_RESOURCE" for v in agg.snapshot().values())


# --- state machine fail-closed ----------------------------------------------
def test_state_machine_rejects_illegal_jump():
    m = ResourceLiveStateMachine(resource=ExternalStagingResource.DATABASE)
    with pytest.raises(IllegalStateTransitionError):
        m.transition(ResourceLiveState.QUALIFIED_EXTERNAL_STAGING)  # skip to success
    m.transition(ResourceLiveState.ACQUISITION_LOCKED)
    assert m.state == ResourceLiveState.ACQUISITION_LOCKED


def test_state_machine_requires_full_adjacent_path_to_qualify():
    m = ResourceLiveStateMachine(resource=ExternalStagingResource.SECRET_PROVIDER)
    assert not m.is_qualified
    for nxt in (
        ResourceLiveState.ACQUISITION_LOCKED,
        ResourceLiveState.CREDENTIAL_CACHED,
        ResourceLiveState.ACCOUNT_VERIFIED,
        ResourceLiveState.HUMAN_INPUT_INTAKE,
        ResourceLiveState.HUMAN_AUTHORIZED,
        ResourceLiveState.PROVIDER_INIT,
        ResourceLiveState.PROVIDER_VALIDATE,
        ResourceLiveState.PROVIDER_PLAN,
        ResourceLiveState.CONNECTIVITY_CHECKING,
        ResourceLiveState.CONNECTIVITY_VERIFIED,
        ResourceLiveState.ISOLATION_CHECKING,
        ResourceLiveState.REGISTRATION,
        ResourceLiveState.RUNTIME_DEPLOY,
        ResourceLiveState.QUALIFIED_EXTERNAL_STAGING,
    ):
        m.transition(nxt)
    assert m.is_qualified
    assert m.is_terminal


# --- dual-key authorization --------------------------------------------------
def test_ai_cannot_mint_human_authorization_key():
    with pytest.raises(EnterpriseRedLineViolationError):
        HumanAuthorizationKey(token="x", actor_kind="AGENT", actor="ai-1")


def test_dual_key_requires_real_user_human_key():
    mk = MachineSafetyKey(token="m")
    assert DualKeyAuthorization(machine_key=mk).is_authorized is False
    hk = HumanAuthorizationKey(token="h", actor_kind="USER", actor="xuange")
    assert DualKeyAuthorization(machine_key=mk, human_key=hk).is_authorized is True


def test_apply_gate_never_returns_go_and_blocks_production():
    mk = MachineSafetyKey(token="m")
    hk = HumanAuthorizationKey(token="h", actor_kind="USER", actor="xuange")
    dk = DualKeyAuthorization(machine_key=mk, human_key=hk)

    # staging (not production) with dual key -> authorized for STAGING apply, still not a GO
    v = evaluate_live_apply_gate(dk, is_production=False)
    assert v.dual_key_authorized is True
    assert v.is_go_or_approved is False
    assert v.state.value == "AUTHORIZED_FOR_STAGING_APPLY"

    # production -> always blocked
    vp = evaluate_live_apply_gate(dk, is_production=True)
    assert vp.is_production is True
    assert vp.is_go_or_approved is False
    assert vp.state.value == "BLOCKED"

    # no human key -> pending
    vp2 = evaluate_live_apply_gate(DualKeyAuthorization(machine_key=mk), is_production=False)
    assert vp2.dual_key_authorized is False
    assert vp2.state.value == "PENDING_HUMAN_AUTHORIZATION"


# --- deterministic package + validator (anti-fabrication) --------------------
def _build_default_package():
    agg = PartialAggregator()
    return build_live_package(
        phase="3.9.15",
        terminal_state=LIVE_TERMINAL_STATE,
        provider_init_result="FAIL",
        provider_init_evidence={"error": "github egress black-holed", "rc": 1},
        resource_states=agg.snapshot(),
        isolation_snapshot={},
        runtime_live_snapshot={},
        deployment_status="NOT_DEPLOYED",
        e2e_status="NOT_EXECUTED",
        failure_state="NONE",
        evidence_digest="deadbeef",
    )


def test_package_hash_is_deterministic_and_valid():
    p1 = _build_default_package()
    p2 = _build_default_package()
    assert p1.package_hash == p2.package_hash  # deterministic
    assert len(p1.package_hash) == 64
    result = validate_package(p1)
    assert result["valid"] is True
    assert result["real_resources_qualified"] == 0


def test_package_validator_rejects_forged_eight_of_eight():
    p = _build_default_package()
    from agents.external_staging_live import LiveQualificationPackage, deterministic_hash

    forged = LiveQualificationPackage(
        **{**p.__dict__, "resource_states": {r.value: "QUALIFIED_EXTERNAL_STAGING" for r in ALL_RESOURCES}}
    )
    d = forged.__dict__.copy()
    d.pop("built_at", None)
    d.pop("package_hash", None)
    forged.package_hash = deterministic_hash(d)
    with pytest.raises(Exception):
        validate_package(forged)


def test_package_validator_rejects_secret_leakage():
    p = _build_default_package()
    p.provider_init_evidence = {"api_secret": "AKID-REAL-SECRET-VALUE-1234567890abcdef"}
    with pytest.raises(Exception):
        validate_package(p)


# --- NEW 3.9.15 provider acquisition capability -----------------------------
def test_classify_init_acquired():
    c = classify_init(0, "", 200, 200)
    assert c == ProviderInitClassification.ACQUIRED


def test_classify_init_blocked():
    c = classify_init(1, "could not query provider registry ... CONNECT tunnel failed ... 502", None, 200)
    assert c == ProviderInitClassification.BINARY_EGRESS_BLOCKED


def test_classify_init_intermittent():
    c = classify_init(1, "Client.Timeout exceeded while awaiting headers ... request canceled", 200, 200)
    assert c == ProviderInitClassification.BINARY_EGRESS_INTERMITTENT


def test_report_real_apply_always_false_even_when_live_succeeds():
    rep = ProviderAcquisitionReport()
    rep.terraform_init_live = True
    rep.terraform_validate_live = True
    rep.terraform_plan_live = True
    assert rep.real_apply_allowed is False
    assert rep.terminal_state == LIVE_TERMINAL_STATE
    assert "GO" not in rep.terminal_state or "BUILT_NO_GO" in rep.terminal_state


def test_assess_feasibility_offline_blocks_without_forge():
    f = assess_acquisition_feasibility()
    assert f.verdict == "TRACK_B_ENVIRONMENT_BLOCKED_PROVIDER_BINARY_EGRESS"
    assert f.native_egress is False


def test_build_report_offline_is_fail_closed():
    rep = build_report(live=False)
    assert rep.terraform_init_live is False
    assert rep.terraform_validate_live is False
    assert rep.terraform_plan_live is False
    assert rep.real_apply_allowed is False
    assert rep.feasibility is not None
    assert rep.feasibility.verdict == "TRACK_B_ENVIRONMENT_BLOCKED_PROVIDER_BINARY_EGRESS"
