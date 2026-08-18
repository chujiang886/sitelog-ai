"""BOIP Phase 3.9.15 — External Staging Real Resource Onboarding & Live Qualification.

Fail-closed live-qualification engine. All real provisioning is out of scope for AI;
this package only models state, records honest evidence, and enforces dual-key
authorization. Real resource 8/8 is NOT a software-phase closure criterion.
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
from .connectivity import ConnectivityCheck, ConnectivityStatus
from .evidence_chain import EvidenceChain, EvidenceEntry
from .failure_recovery import FailureRecoveryRecord, FailureRecoveryState
from .human_input import HumanInputIntake
from .isolation import IsolationMatrix, IsolationStatus
from .live_package import (
    LiveQualificationPackage,
    build_live_package,
    deterministic_hash,
)
from .package_validator import PackageValidationError, validate_package
from .apply_gate import (
    LiveApplyGateState,
    LiveApplyGateVerdict,
    evaluate_live_apply_gate,
)
from .partial_aggregator import PartialAggregator
from .provider_account_verification import (
    ProviderAccountVerification,
    ProviderAccountVerificationStatus,
)
from .real_e2e import RealE2ERecord, RealE2EStatus
from .resource_state_machine import (
    IllegalStateTransitionError,
    ResourceLiveStateMachine,
)
from .runtime_deployment import RuntimeDeploymentRecord, RuntimeDeploymentStatus
from .runtime_live import RuntimeLiveMatrix, RuntimeLiveStatus

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
    "ProviderAccountVerification",
    "ProviderAccountVerificationStatus",
    "HumanInputIntake",
    "ConnectivityCheck",
    "ConnectivityStatus",
    "IsolationMatrix",
    "IsolationStatus",
    "RuntimeDeploymentRecord",
    "RuntimeDeploymentStatus",
    "RuntimeLiveMatrix",
    "RuntimeLiveStatus",
    "LiveQualificationPackage",
    "build_live_package",
    "deterministic_hash",
    "PackageValidationError",
    "validate_package",
    "LiveApplyGateState",
    "LiveApplyGateVerdict",
    "evaluate_live_apply_gate",
    "RealE2ERecord",
    "RealE2EStatus",
    "FailureRecoveryRecord",
    "FailureRecoveryState",
    "EvidenceChain",
    "EvidenceEntry",
    "MachineSafetyKey",
    "HumanAuthorizationKey",
    "DualKeyAuthorization",
    "ApplyGateState",
    "ChangeControlVerdict",
    "EnterpriseRedLineViolationError",
    "AuditActorKind",
    "require_human_actor",
]
