"""Phase 3.9.15 — Live Qualification Orchestrator (T30/T31/T35).

Assembles the full, honest live-qualification evidence set and produces a
tamper-evident ``LiveQualificationPackage``:

  - T0 baseline (project status / phase boundary read, honest)
  - T2/T3/T4/T5 provider init / validate / plan evidence via ``provider_acquisition``
  - T13–T24 8-resource live onboarding (0/8 by default, evidence-gated)
  - 9 isolation dimensions (NOT_VERIFIED by default)
  - 13 runtime live checks (NOT_EXECUTED by default)
  - T8 plan-safety scan of committed IaC
  - dual-key + apply-gate + change-control fail-closed verdicts
  - deterministic package hash + fail-closed validator

The orchestrator NEVER performs any real provisioning, credential injection, or
production action. It accepts an injected acquisition report for deterministic
testing (do not run real ``terraform init`` in unit tests).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .apply_gate import evaluate_live_apply_gate
from .change_control import DualKeyAuthorization
from .constants import (
    ALL_ISOLATION_DIMENSIONS,
    ALL_RESOURCES,
    ALL_RUNTIME_LIVE_CHECKS,
    LIVE_TERMINAL_STATE,
    PHASE,
)
from .human_authorization import (
    evaluate_live_change_control,
    generate_machine_safety_key,
    make_dual_key,
)
from .live_package import LiveQualificationPackage, build_live_package
from .live_resource_onboarding import (
    ResourceOnboardingDriver,
    ResourceOnboardingEvidence,
)
from .package_validator import PackageValidationError, validate_package
from .plan_safety import PlanSafetyScanner
from .provider_acquisition import ProviderAcquisitionReport, build_report

_NOT_VERIFIED = "NOT_VERIFIED"
_NOT_EXECUTED = "NOT_EXECUTED"

# Acquisition verdicts that, when no real init PASS occurred, map to a BLOCKED
# (environment) provider-init result rather than a generic FAIL.
_BLOCKED_VERDICTS = {
    "PROVIDER_BINARY_EGRESS_BLOCKED",
    "PROVIDER_BINARY_EGRESS_INTERMITTENT",
    "TRACK_B_ENVIRONMENT_BLOCKED_PROVIDER_BINARY_EGRESS",
    "OFFLINE_OR_TOOLCHAIN_UNAVAILABLE",
}


@dataclass
class LiveQualificationReport:
    phase: str = PHASE
    terminal_state: str = LIVE_TERMINAL_STATE
    built_no_go: bool = True
    real_apply_allowed: bool = False
    provider_acquisition: Optional[Dict[str, Any]] = None
    resource_states: Dict[str, str] = field(default_factory=dict)
    resource_blockers: Dict[str, list] = field(default_factory=dict)
    qualified_count: int = 0
    resource_total: int = 8
    isolation_snapshot: Dict[str, str] = field(default_factory=dict)
    runtime_live_snapshot: Dict[str, str] = field(default_factory=dict)
    plan_safety: Dict[str, Any] = field(default_factory=dict)
    change_control: Optional[Dict[str, Any]] = None
    apply_gate: Optional[Dict[str, Any]] = None
    package: Optional[LiveQualificationPackage] = None
    package_validation: Optional[Dict[str, Any]] = None
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "terminal_state": self.terminal_state,
            "built_no_go": self.built_no_go,
            "real_apply_allowed": self.real_apply_allowed,
            "provider_acquisition": self.provider_acquisition,
            "resource_states": self.resource_states,
            "resource_blockers": self.resource_blockers,
            "qualified_count": self.qualified_count,
            "resource_total": self.resource_total,
            "isolation_snapshot": self.isolation_snapshot,
            "runtime_live_snapshot": self.runtime_live_snapshot,
            "plan_safety": self.plan_safety,
            "change_control": self.change_control,
            "apply_gate": self.apply_gate,
            "package": self.package.__dict__ if self.package else None,
            "package_validation": self.package_validation,
            "generated_at": self.generated_at,
        }


def _provider_init_result(rep: ProviderAcquisitionReport) -> str:
    if rep.terraform_init_live:
        return "PASS"
    if rep.verdict in _BLOCKED_VERDICTS:
        return "BLOCKED"
    return "FAIL"


def _safe_provider_evidence(rep: ProviderAcquisitionReport) -> Dict[str, Any]:
    """Curated, secret-free evidence for the package (raw stdout/stderr stripped)."""
    init = rep.init
    return {
        "terraform_init_live": rep.terraform_init_live,
        "terraform_validate_live": rep.terraform_validate_live,
        "terraform_plan_live": rep.terraform_plan_live,
        "verdict": rep.verdict,
        "init_command": init.command if init else None,
        "init_rc": init.rc if init else None,
        "init_classification": init.classification.value if init else None,
        "init_registry_probe_http": init.registry_probe_http if init else None,
        "init_github_probe_http": init.github_probe_http if init else None,
        "validate_rc": rep.validate.rc if rep.validate else None,
        "validate_passed": rep.validate.passed if rep.validate else False,
        "plan_rc": rep.plan.rc if rep.plan else None,
        "feasibility": rep.feasibility.to_dict() if rep.feasibility else None,
    }


def _evidence_digest(rep: LiveQualificationReport) -> str:
    payload = {
        "provider": rep.provider_acquisition,
        "resources": rep.resource_states,
        "isolation": rep.isolation_snapshot,
        "runtime": rep.runtime_live_snapshot,
        "plan_safety": rep.plan_safety,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_live_qualification_report(
    live: bool = False,
    acquisition_report: Optional[ProviderAcquisitionReport] = None,
    staging_dir: str = "infrastructure/staging",
    timeout: int = 60,
) -> LiveQualificationReport:
    """Build the full live-qualification report + package (fail-closed, honest)."""
    rep = LiveQualificationReport()

    # --- T2/T3/T4/T5 provider acquisition (real run only when live=True) ---
    acq = acquisition_report if acquisition_report is not None else build_report(
        staging_dir=staging_dir, live=live, timeout=timeout
    )
    rep.provider_acquisition = acq.to_dict()

    # --- T13–T24 8-resource live onboarding (default: empty evidence -> 0/8) ---
    driver = ResourceOnboardingDriver()
    driver.drive_all({r: ResourceOnboardingEvidence() for r in ALL_RESOURCES})
    agg = driver.aggregator
    rep.resource_states = agg.snapshot()
    rep.resource_blockers = driver.blockers
    rep.qualified_count = agg.qualified_count()
    rep.resource_total = agg.total()

    # --- 9 isolation dimensions (NOT_VERIFIED) ---
    rep.isolation_snapshot = {d.value: _NOT_VERIFIED for d in ALL_ISOLATION_DIMENSIONS}

    # --- 13 runtime live checks (NOT_EXECUTED) ---
    rep.runtime_live_snapshot = {c.value: _NOT_EXECUTED for c in ALL_RUNTIME_LIVE_CHECKS}

    # --- T8 plan safety (read-only static scan of committed IaC) ---
    scanner = PlanSafetyScanner(staging_dir=staging_dir)
    findings = scanner.scan()
    rep.plan_safety = {
        "verdict": scanner.verdict(),
        "has_high": scanner.has_high(),
        "findings_count": len(findings),
    }

    # --- dual-key + apply gate + change control (no human key => pending) ---
    # AI never mints the Human Authorization Key; only the machine safety key exists.
    mk = generate_machine_safety_key()
    dk: DualKeyAuthorization = make_dual_key(mk, human_key=None)
    rep.change_control = evaluate_live_change_control(dk).to_dict()
    gate = evaluate_live_apply_gate(dk, is_production=False)
    rep.apply_gate = {
        "state": gate.state.value,
        "is_go_or_approved": gate.is_go_or_approved,
        "is_production": gate.is_production,
        "dual_key_authorized": gate.dual_key_authorized,
        "detail": gate.detail,
    }

    # --- build + validate package (fail-closed; honest 0/8) ---
    provider_init_result = _provider_init_result(acq)
    pkg = build_live_package(
        phase=PHASE,
        terminal_state=LIVE_TERMINAL_STATE,
        provider_init_result=provider_init_result,
        provider_init_evidence=_safe_provider_evidence(acq),
        resource_states=rep.resource_states,
        isolation_snapshot=rep.isolation_snapshot,
        runtime_live_snapshot=rep.runtime_live_snapshot,
        deployment_status="NOT_DEPLOYED",
        e2e_status="NOT_EXECUTED",
        failure_state="NONE",
        evidence_digest=_evidence_digest(rep),
    )
    rep.package = pkg
    try:
        rep.package_validation = validate_package(pkg)
    except PackageValidationError as e:
        rep.package_validation = {"valid": False, "error": str(e)}

    rep.generated_at = datetime.now(timezone.utc).isoformat()
    return rep
