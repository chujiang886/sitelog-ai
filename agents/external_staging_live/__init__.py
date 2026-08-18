"""BOIP Phase 3.9.15 — External Staging Real Resource Onboarding & Live Qualification.

Fail-closed live-qualification engine. All real provisioning is out of scope for AI;
this package only models state, records honest evidence, and enforces dual-key
authorization. Real resource 8/8 is NOT a software-phase closure criterion.

Only modules that are COMMITTED in this branch are imported here. Runtime Gate,
Resource Registry, Human Authorization, Deployment Provider and Isolation Guard are
reused from ``agents/staging_runtime/`` and ``agents/external_staging_runtime/`` (3.9.14)
and are intentionally NOT re-implemented in this package.
"""
from __future__ import annotations

from .change_control import (
    ApplyGateState,
    AuditActorKind,
    ChangeControlVerdict,
    DualKeyAuthorization,
    EnterpriseRedLineViolationError,
    HumanAuthorizationKey,
    MachineSafetyKey,
    require_human_actor,
)
from .constants import (
    ALL_ISOLATION_DIMENSIONS,
    ALL_RESOURCES,
    ALL_RUNTIME_LIVE_CHECKS,
    BUILT_NO_GO,
    ExternalStagingResource,
    FAILURE_STATES,
    IsolationDimension,
    LIVE_TERMINAL_STATE,
    PHASE,
    PHASE_NAME,
    ResourceLiveState,
    RuntimeLiveCheck,
    TERMINAL_SUCCESS,
    ALLOWED_TRANSITIONS,
)
from .partial_aggregator import PartialAggregator
from .resource_state_machine import (
    IllegalStateTransitionError,
    ResourceLiveStateMachine,
)
from .live_package import (
    LiveQualificationPackage,
    build_live_package,
    deterministic_hash,
)
from .plan_safety import (
    PlanSafetyScanner,
    SafetyFinding,
    SEV_HIGH,
    SEV_MED,
    SEV_LOW,
)
from .package_validator import PackageValidationError, validate_package
from .apply_gate import (
    LiveApplyGateState,
    LiveApplyGateVerdict,
    evaluate_live_apply_gate,
)
from .provider_acquisition import (
    AcquisitionFeasibility,
    LivePlanEvidence,
    ProviderAcquisitionReport,
    ProviderInitClassification,
    ProviderInitEvidence,
    ValidateEvidence,
    assess_acquisition_feasibility,
    build_report,
    classify_init,
)

__all__ = [
    "PHASE",
    "PHASE_NAME",
    "LIVE_TERMINAL_STATE",
    "BUILT_NO_GO",
    "ExternalStagingResource",
    "ALL_RESOURCES",
    "ResourceLiveState",
    "FAILURE_STATES",
    "TERMINAL_SUCCESS",
    "ALLOWED_TRANSITIONS",
    "IsolationDimension",
    "ALL_ISOLATION_DIMENSIONS",
    "RuntimeLiveCheck",
    "ALL_RUNTIME_LIVE_CHECKS",
    "ResourceLiveStateMachine",
    "IllegalStateTransitionError",
    "PartialAggregator",
    "LiveQualificationPackage",
    "build_live_package",
    "deterministic_hash",
    "PlanSafetyScanner",
    "SafetyFinding",
    "SEV_HIGH",
    "SEV_MED",
    "SEV_LOW",
    "PackageValidationError",
    "validate_package",
    "LiveApplyGateState",
    "LiveApplyGateVerdict",
    "evaluate_live_apply_gate",
    "MachineSafetyKey",
    "HumanAuthorizationKey",
    "DualKeyAuthorization",
    "ApplyGateState",
    "ChangeControlVerdict",
    "EnterpriseRedLineViolationError",
    "AuditActorKind",
    "require_human_actor",
    "ProviderInitEvidence",
    "ProviderInitClassification",
    "ValidateEvidence",
    "LivePlanEvidence",
    "AcquisitionFeasibility",
    "ProviderAcquisitionReport",
    "classify_init",
    "assess_acquisition_feasibility",
    "build_report",
]
