"""8-Resource Live State Machine — fail-closed, no forgery.

Per resource, tracks a state on the canonical 15+4 transition graph.
Illegal jumps (skipping, backward-to-success, or into a non-adjacent state)
are rejected. The machine enforces *structural* validity only; authorization
(dual-key, human actor) is enforced by the change-control gate elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    ALLOWED_TRANSITIONS,
    ExternalStagingResource,
    FAILURE_STATES,
    ResourceLiveState,
    TERMINAL_SUCCESS,
)


class IllegalStateTransitionError(Exception):
    """Fail-closed: the requested state jump is not on the allowed map."""


@dataclass
class ResourceLiveStateMachine:
    resource: ExternalStagingResource
    state: ResourceLiveState = ResourceLiveState.PENDING_EXTERNAL_STAGING_RESOURCE
    history: list = field(default_factory=list)
    last_evidence: Optional[dict] = None

    def can_transition(self, to: ResourceLiveState) -> bool:
        return to in ALLOWED_TRANSITIONS.get(self.state, set())

    def transition(
        self, to: ResourceLiveState, evidence: Optional[dict] = None
    ) -> "ResourceLiveStateMachine":
        if to == self.state:
            return self
        if not self.can_transition(to):
            raise IllegalStateTransitionError(
                f"[{self.resource.value}] illegal transition "
                f"{self.state.value} -> {to.value}"
            )
        self.history.append((self.state.value, to.value))
        self.state = to
        self.last_evidence = evidence
        return self

    # --- read-only predicates -------------------------------------------------
    @property
    def is_qualified(self) -> bool:
        return self.state == TERMINAL_SUCCESS

    @property
    def is_failure(self) -> bool:
        return self.state in FAILURE_STATES

    @property
    def is_blocked(self) -> bool:
        return self.state == ResourceLiveState.BLOCKED

    @property
    def is_terminal(self) -> bool:
        return self.state == TERMINAL_SUCCESS or self.state in FAILURE_STATES
