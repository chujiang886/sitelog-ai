"""Phase 3.9.15 — Live onboarding driver, human authorization, orchestrator (fail-closed).

Tests the SOFTWARE guarantees of the 3.9.15 upper-layer capabilities:

- #402 Provider-init report verdict is HONEST: when init passes but validate
  and/or plan fail, the verdict is NOT "OK"; init/validate/plan flags are real;
  real_apply_allowed is ALWAYS False.
- Live resource onboarding is evidence-gated: with no real evidence every
  resource stays PENDING (0/8) and records a blocker; with full (structural
  only, injected) evidence a resource walks to QUALIFIED without forgery.
- Human authorization: the Machine Safety Key is system-generatable; AI cannot
  mint a Human Authorization Key; without a human key the live change-control
  verdict is PENDING with real_apply_allowed=False and terminal=BUILT_NO_GO.
- Orchestrator: assembles 0/8 + 9 NOT_VERIFIED + 13 NOT_EXECUTED + plan-safety
  + dual-key + apply-gate + change-control, builds a package that passes the
  fail-closed validator, and reports BUILT_NO_GO / real_apply_allowed=False.

No real provisioning, credential, or production action is performed.
"""
from __future__ import annotations

import pytest

from agents.external_staging_live import (
    ALL_RESOURCES,
    LIVE_TERMINAL_STATE,
    ProviderAcquisitionReport,
    ResourceOnboardingDriver,
    ResourceOnboardingEvidence,
    build_live_qualification_report,
    evaluate_live_change_control,
    generate_machine_safety_key,
    make_dual_key,
    wrap_human_authorization_key,
)
from agents.external_staging_live.change_control import EnterpriseRedLineViolationError
from agents.external_staging_live.constants import ALL_ISOLATION_DIMENSIONS, ALL_RUNTIME_LIVE_CHECKS
from agents.external_staging_live.provider_acquisition import build_report


# --- #402 verdict honesty ----------------------------------------------------
def _patch_toolchain_and_runs(monkeypatch, init_rc, validate_rc, plan_rc):
    """Force build_report to reach the init/validate/plan branch in a no-terraform sandbox."""
    import agents.external_staging_live.provider_acquisition as pa

    # build_report imports discover_toolchain from iac_executor; patch the source.
    from agents.external_staging_runtime.iac_executor import ToolchainInfo

    monkeypatch.setattr(
        pa, "discover_toolchain",
        lambda: ToolchainInfo(binary="/usr/bin/terraform", flavour="terraform",
                              version="1.2.3", available=True),
    )
    monkeypatch.setattr(pa, "run_init", lambda *a, **k: (init_rc, "out", "", 1.0))
    monkeypatch.setattr(pa, "run_validate", lambda *a, **k: (validate_rc, "out", ""))
    monkeypatch.setattr(pa, "run_plan", lambda *a, **k: (plan_rc, "Plan: 0 to add", "", 0, 0))


def test_build_report_honest_verdict_when_validate_and_plan_fail(monkeypatch):
    _patch_toolchain_and_runs(monkeypatch, init_rc=0, validate_rc=1, plan_rc=1)
    rep = build_report(live=True, staging_dir="infrastructure/staging", timeout=10)
    assert rep.terraform_init_live is True
    assert rep.terraform_validate_live is False
    assert rep.terraform_plan_live is False
    assert rep.real_apply_allowed is False
    assert rep.verdict == "PROVIDER_ACQUIRED_INIT_ONLY_VALIDATE_PLAN_FAILED"
    assert "OK" not in rep.verdict


def test_build_report_honest_verdict_when_plan_fails_only(monkeypatch):
    _patch_toolchain_and_runs(monkeypatch, init_rc=0, validate_rc=0, plan_rc=1)
    rep = build_report(live=True, staging_dir="infrastructure/staging", timeout=10)
    assert rep.terraform_init_live and rep.terraform_validate_live
    assert rep.terraform_plan_live is False
    assert rep.verdict == "PROVIDER_ACQUIRED_INIT_VALIDATE_OK_PLAN_FAILED"
    # honest: must NOT falsely claim the unified init+validate+plan OK verdict
    assert rep.verdict != "PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK"


def test_build_report_honest_verdict_when_all_pass(monkeypatch):
    _patch_toolchain_and_runs(monkeypatch, init_rc=0, validate_rc=0, plan_rc=0)
    rep = build_report(live=True, staging_dir="infrastructure/staging", timeout=10)
    assert rep.terraform_init_live and rep.terraform_validate_live and rep.terraform_plan_live
    assert rep.verdict == "PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK"


# --- live resource onboarding (evidence-gated) ------------------------------
def test_driver_default_all_pending_zero_of_eight():
    d = ResourceOnboardingDriver()
    d.drive_all({r: ResourceOnboardingEvidence() for r in ALL_RESOURCES})
    assert d.qualified_count() == 0
    assert d.total() == 8
    assert all(v == "PENDING_EXTERNAL_STAGING_RESOURCE" for v in d.snapshot().values())
    # every resource records a blocker (missing real evidence)
    assert all(d.blockers[r.value] for r in ALL_RESOURCES)


def test_driver_happy_path_is_structural_only():
    ev = ResourceOnboardingEvidence(
        acquisition_locked=True,
        credential_cached=True,
        account_verified=True,
        human_input_received=True,
        human_authorized=True,
        provider_init_passed=True,
        provider_validate_passed=True,
        provider_plan_passed=True,
        connectivity_checking=True,
        connectivity_verified=True,
        isolation_checking=True,
        isolation_verified=True,
        registered=True,
        runtime_deployed=True,
    )
    d = ResourceOnboardingDriver()
    d.drive_resource(ALL_RESOURCES[0], ev)
    machine = d.aggregator.machines[ALL_RESOURCES[0]]
    assert machine.is_qualified
    assert d.blockers[ALL_RESOURCES[0].value] == []


def test_driver_stops_at_first_missing_evidence():
    ev = ResourceOnboardingEvidence(acquisition_locked=True, credential_cached=True)
    d = ResourceOnboardingDriver()
    d.drive_resource(ALL_RESOURCES[1], ev)
    state = d.aggregator.machines[ALL_RESOURCES[1]].state
    # advanced exactly 2 steps, then blocked
    assert state.value == "CREDENTIAL_CACHED"
    assert d.blockers[ALL_RESOURCES[1].value]


# --- human authorization (fail-closed) --------------------------------------
def test_machine_safety_key_generatable_but_human_key_not():
    mk = generate_machine_safety_key()
    assert mk.generated_by == "machine"
    # AI cannot mint a human key: wrapper rejects non-USER actor
    with pytest.raises(EnterpriseRedLineViolationError):
        wrap_human_authorization_key(
            __import__(
                "agents.external_staging_live.change_control", fromlist=["HumanAuthorizationKey"]
            ).HumanAuthorizationKey(token="x", actor_kind="AGENT", actor="ai")
        )


def test_live_change_control_pending_without_human_key():
    mk = generate_machine_safety_key()
    dk = make_dual_key(mk, human_key=None)
    v = evaluate_live_change_control(dk)
    assert v.real_apply_allowed is False
    assert v.is_go_or_approved is False
    assert v.dual_key_authorized is False
    assert v.terminal_state == LIVE_TERMINAL_STATE


# --- orchestrator ------------------------------------------------------------
def _fake_report(init_live, validate_live, plan_live, verdict):
    rep = ProviderAcquisitionReport()
    rep.terraform_init_live = init_live
    rep.terraform_validate_live = validate_live
    rep.terraform_plan_live = plan_live
    rep.verdict = verdict
    rep.real_apply_allowed = False
    return rep


def test_orchestrator_zero_of_eight_built_no_go():
    rep = build_live_qualification_report(
        live=False,
        acquisition_report=_fake_report(False, False, False, "OFFLINE_OR_TOOLCHAIN_UNAVAILABLE"),
    )
    assert rep.qualified_count == 0
    assert rep.resource_total == 8
    assert rep.real_apply_allowed is False
    assert rep.terminal_state == LIVE_TERMINAL_STATE
    assert rep.package is not None
    assert rep.package.real_resources_qualified == 0
    # package validation passes (honest 0/8)
    assert rep.package_validation is not None
    assert rep.package_validation.get("valid") is True
    # 9 isolation NOT_VERIFIED, 13 runtime NOT_EXECUTED
    assert len(rep.isolation_snapshot) == len(ALL_ISOLATION_DIMENSIONS)
    assert all(v == "NOT_VERIFIED" for v in rep.isolation_snapshot.values())
    assert len(rep.runtime_live_snapshot) == len(ALL_RUNTIME_LIVE_CHECKS)
    assert all(v == "NOT_EXECUTED" for v in rep.runtime_live_snapshot.values())
    # change control pending (no human key), real apply forbidden
    assert rep.change_control["dual_key_authorized"] is False
    assert rep.change_control["real_apply_allowed"] is False
    assert rep.change_control["terminal_state"] == LIVE_TERMINAL_STATE
    # apply gate never a GO, never production
    assert rep.apply_gate["is_go_or_approved"] is False
    assert rep.apply_gate["is_production"] is False


def test_orchestrator_provider_init_pass_still_zero_resources():
    rep = build_live_qualification_report(
        live=False,
        acquisition_report=_fake_report(
            True, True, True, "PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK"
        ),
    )
    assert rep.package.provider_init_result == "PASS"
    assert rep.qualified_count == 0
    # 0/8 is allowed even when init PASS; validator must pass
    assert rep.package_validation.get("valid") is True
