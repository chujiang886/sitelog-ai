"""Phase 3.9.15 live-qualification change control — reuses the 3.9.14 base.

Dual-key authorization (Machine Safety Key + Human Authorization Key) is inherited
unchanged. The Human Authorization Key is **always** required to be minted by a
`USER` actor; AI must never mint it. This module only re-exports the base classes
and pins the Phase 3.9.15 terminal state.
"""
from __future__ import annotations

from agents.external_staging_runtime.change_control import (
    ApplyGateState,
    AuditActorKind,
    ChangeControlVerdict,
    DualKeyAuthorization,
    EnterpriseRedLineViolationError,
    HumanAuthorizationKey,
    MachineSafetyKey,
    evaluate_change_control,
    require_human_actor,
)

from .constants import LIVE_TERMINAL_STATE

__all__ = [
    "MachineSafetyKey",
    "HumanAuthorizationKey",
    "DualKeyAuthorization",
    "ApplyGateState",
    "ChangeControlVerdict",
    "evaluate_change_control",
    "EnterpriseRedLineViolationError",
    "AuditActorKind",
    "require_human_actor",
    "LIVE_TERMINAL_STATE",
]
