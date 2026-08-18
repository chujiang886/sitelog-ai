"""Phase 3.9.15 External Staging Real Resource Live Qualification — fail-closed tests.

These tests assert the SOFTWARE guarantees of the live-qualification engine:

- The terminal state is BUILT_NO_GO and contains no forbidden GO/APPROVED/PRODUCTION_READY.
- The 8-resource aggregator honestly reports 0/8 by default (no forgery).
- The 8-resource state machine rejects illegal jumps and never reaches QUALIFIED without
  the full allowed path.
- Dual-key authorization: AI cannot mint a Human Authorization Key; staging apply is never
  a GO; production apply is BLOCKED.
- The deterministic package hash is reproducible and passes the fail-closed validator, and
  an 8/8 claim without real deploy + real E2E evidence is rejected (anti-fabrication).

No real provisioning, credential, or production action is performed by these tests.
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
    IsolationMatrix,
    IsolationDimension,
    MachineSafetyKey,
    PartialAggregator,
    ProviderAccountVerificationStatus,
    ResourceLiveState,
    ResourceLiveStateMachine,
    RuntimeDeploymentRecord,
    RuntimeDeploymentStatus,
    RuntimeLiveMatrix,
    build_live_package,
    evaluate_live_apply_gate,
    validate_package,
)
from agents.external_staging_live.change_control import EnterpriseRedLineViolationError


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
    # a single legal step is allowed
    m.transition(ResourceLiveState.ACQUISITION_LOCKED)
    assert m.state == ResourceLiveState.ACQUISITION_LOCKED


def test_state_machine_cannot_reach_qualified_by_default():
    m = ResourceLiveStateMachine(resource=ExternalStagingResource.SECRET_PROVIDER)
    assert not m.is_qualified
    # simulate the full allowed path would still require human + dual-key at runtime,
    # but structurally each transition must be adjacent.
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


# --- provider account / deployment defaults ----------------------------------
def test_provider_account_unverified_by_default():
    from agents.external_staging_live import ProviderAccountVerification

    v = ProviderAccountVerification(resource=ExternalStagingResource.DATABASE)
    assert v.status == ProviderAccountVerificationStatus.UNVERIFIED
    assert v.account_id is None


def test_runtime_deployment_not_deployed_by_default():
    d = RuntimeDeploymentRecord()
    assert d.status == RuntimeDeploymentStatus.NOT_DEPLOYED
    assert d.real_apply_executed is False


# --- isolation / runtime live matrices ---------------------------------------
def test_isolation_matrix_defaults_not_verified():
    iso = IsolationMatrix()
    assert iso.verified_count() == 0
    assert iso.all_verified() is False
    iso.verify(IsolationDimension.NETWORK_SEGMENT, {"by": "xuange"})
    assert iso.verified_count() == 1
    assert iso.all_verified() is False


def test_runtime_live_matrix_defaults_not_passed():
    rtl = RuntimeLiveMatrix()
    assert rtl.passed_count() == 0
    assert rtl.all_passed() is False


# --- deterministic package + validator (anti-fabrication) --------------------
def _build_default_package():
    agg = PartialAggregator()
    iso = IsolationMatrix()
    rtl = RuntimeLiveMatrix()
    return build_live_package(
        phase="3.9.15",
        terminal_state=LIVE_TERMINAL_STATE,
        provider_init_result="FAIL",
        provider_init_evidence={"error": "github egress black-holed", "rc": 1},
        resource_states=agg.snapshot(),
        isolation_snapshot=iso.snapshot(),
        runtime_live_snapshot=rtl.snapshot(),
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
    # forge an 8/8 claim without real deploy + real E2E
    from agents.external_staging_live import LiveQualificationPackage

    forged = LiveQualificationPackage(**{**p.__dict__, "resource_states": {r.value: "QUALIFIED_EXTERNAL_STAGING" for r in ALL_RESOURCES}})
    # recompute hash so the tamper check passes, but the honesty check must still fail
    from agents.external_staging_live import deterministic_hash

    d = forged.__dict__.copy(); d.pop("built_at", None); d.pop("package_hash", None)
    forged.package_hash = deterministic_hash(d)
    with pytest.raises(Exception):
        validate_package(forged)


def test_package_validator_rejects_secret_leakage():
    p = _build_default_package()
    p.provider_init_evidence = {"api_secret": "AKID-REAL-SECRET-VALUE-1234567890abcdef"}
    with pytest.raises(Exception):
        validate_package(p)
