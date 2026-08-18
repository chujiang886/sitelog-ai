"""Phase 3.9.15 — Live Resource Onboarding Driver (T13–T24).

Evidence-gated, fail-closed per-resource driver over the canonical 8-Resource
Live State Machine (15 happy + 4 failure = 19 states). The driver NEVER
fabricates qualification: a resource only advances when the corresponding real
evidence flag is present. With no real human input / dual-key / connectivity /
isolation / runtime evidence (the default in this software phase), every
resource stays PENDING and the honest aggregate is 0/8.

This module does NOT re-implement the Runtime Gate, Resource Registry, Human
Authorization, Deployment Provider, or Isolation Guard — those are reused from
``agents/staging_runtime/`` and ``agents/external_staging_runtime/``. It only
models the per-resource state progression specific to 3.9.15's live
qualification, reusing ``ResourceLiveStateMachine`` and ``PartialAggregator``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .constants import ALL_RESOURCES, ExternalStagingResource, ResourceLiveState
from .partial_aggregator import PartialAggregator
from .resource_state_machine import (
    IllegalStateTransitionError,
    ResourceLiveStateMachine,
)


@dataclass
class ResourceOnboardingEvidence:
    """Real evidence required to advance each resource.

    All flags default ``False`` (honest no-forgery). Each flag gates exactly one
    forward transition on the canonical state graph. A ``False`` flag means the
    corresponding real-world step has NOT happened, so the driver stops at the
    current state and records a blocker (never skips ahead).
    """

    acquisition_locked: bool = False
    credential_cached: bool = False
    account_verified: bool = False
    human_input_received: bool = False
    human_authorized: bool = False
    provider_init_passed: bool = False
    provider_validate_passed: bool = False
    provider_plan_passed: bool = False
    connectivity_checking: bool = False
    connectivity_verified: bool = False
    isolation_checking: bool = False
    isolation_verified: bool = False
    registered: bool = False
    runtime_deployed: bool = False


# Canonical forward path: (next_state, evidence_flag that unlocks it).
# `can_transition` additionally enforces adjacency, so even a forged evidence
# bundle cannot skip states.
_STEP_TO_EVIDENCE: List[tuple[ResourceLiveState, str]] = [
    (ResourceLiveState.ACQUISITION_LOCKED, "acquisition_locked"),
    (ResourceLiveState.CREDENTIAL_CACHED, "credential_cached"),
    (ResourceLiveState.ACCOUNT_VERIFIED, "account_verified"),
    (ResourceLiveState.HUMAN_INPUT_INTAKE, "human_input_received"),
    (ResourceLiveState.HUMAN_AUTHORIZED, "human_authorized"),
    (ResourceLiveState.PROVIDER_INIT, "provider_init_passed"),
    (ResourceLiveState.PROVIDER_VALIDATE, "provider_validate_passed"),
    (ResourceLiveState.PROVIDER_PLAN, "provider_plan_passed"),
    (ResourceLiveState.CONNECTIVITY_CHECKING, "connectivity_checking"),
    (ResourceLiveState.CONNECTIVITY_VERIFIED, "connectivity_verified"),
    (ResourceLiveState.ISOLATION_CHECKING, "isolation_checking"),
    (ResourceLiveState.REGISTRATION, "isolation_verified"),
    (ResourceLiveState.RUNTIME_DEPLOY, "registered"),
    (ResourceLiveState.QUALIFIED_EXTERNAL_STAGING, "runtime_deployed"),
]


def advance_resource(
    machine: ResourceLiveStateMachine,
    evidence: Optional[ResourceOnboardingEvidence] = None,
) -> List[str]:
    """Advance ``machine`` as far as real evidence permits.

    Returns the list of blocker strings (empty when fully qualified). The machine
    is mutated in place. Illegal jumps are rejected by ``can_transition`` and
    recorded as a blocker rather than silently skipped.
    """
    ev = evidence or ResourceOnboardingEvidence()
    blockers: List[str] = []
    for target, flag in _STEP_TO_EVIDENCE:
        if not machine.can_transition(target):
            blockers.append(
                f"state-graph does not permit transition to {target.value} "
                f"from {machine.state.value}"
            )
            break
        if getattr(ev, flag):
            try:
                machine.transition(target, evidence={"flag": flag})
            except IllegalStateTransitionError as e:
                blockers.append(str(e))
                break
        else:
            blockers.append(
                f"missing evidence '{flag}' blocks transition to {target.value}"
            )
            break
    return blockers


class ResourceOnboardingDriver:
    """Drives all 8 External Staging resources through their live state machines."""

    def __init__(self) -> None:
        self.aggregator = PartialAggregator()
        self.blockers: Dict[str, List[str]] = {}

    def drive_resource(
        self,
        resource: ExternalStagingResource,
        evidence: Optional[ResourceOnboardingEvidence] = None,
    ) -> ResourceLiveStateMachine:
        machine = self.aggregator.machines[resource]
        self.blockers[resource.value] = advance_resource(machine, evidence)
        return machine

    def drive_all(
        self,
        evidence_map: Optional[Dict[ExternalStagingResource, ResourceOnboardingEvidence]] = None,
    ) -> PartialAggregator:
        evidence_map = evidence_map or {}
        for r in ALL_RESOURCES:
            self.drive_resource(r, evidence_map.get(r))
        return self.aggregator

    def qualified_count(self) -> int:
        return self.aggregator.qualified_count()

    def total(self) -> int:
        return self.aggregator.total()

    def snapshot(self) -> Dict[str, str]:
        return self.aggregator.snapshot()

    def summary(self) -> Dict[str, object]:
        return {
            "qualified_count": self.qualified_count(),
            "total": self.total(),
            "verdict": self.aggregator.verdict(),
            "resource_states": self.snapshot(),
            "blockers": self.blockers,
        }
