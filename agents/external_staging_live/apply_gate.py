"""Live apply gate (T12) — dual-key, fail-closed.

A live (staging) apply is authorized ONLY when both keys are present (machine safety
key + human authorization key minted by a real USER actor) AND the target is NOT
production. The gate never returns a GO / APPROVED verdict: staging apply is not a
production go-live. `is_go_or_approved` is therefore always False.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .change_control import ApplyGateState, DualKeyAuthorization
from .constants import LIVE_TERMINAL_STATE


class LiveApplyGateState(str, Enum):
    PENDING_HUMAN_AUTHORIZATION = "PENDING_HUMAN_AUTHORIZATION"
    AUTHORIZED_FOR_STAGING_APPLY = "AUTHORIZED_FOR_STAGING_APPLY"
    BLOCKED = "BLOCKED"
    DENIED = "DENIED"


@dataclass
class LiveApplyGateVerdict:
    state: LiveApplyGateState
    is_go_or_approved: bool  # always False (fail-closed)
    is_production: bool
    dual_key_authorized: bool
    detail: str


def evaluate_live_apply_gate(
    dual_key: DualKeyAuthorization, is_production: bool = False
) -> LiveApplyGateVerdict:
    if is_production:
        return LiveApplyGateVerdict(
            state=LiveApplyGateState.BLOCKED,
            is_go_or_approved=False,
            is_production=True,
            dual_key_authorized=False,
            detail="Production apply is forbidden by red line; gate BLOCKED.",
        )
    if dual_key.is_authorized:
        return LiveApplyGateVerdict(
            state=LiveApplyGateState.AUTHORIZED_FOR_STAGING_APPLY,
            is_go_or_approved=False,
            is_production=False,
            dual_key_authorized=True,
            detail="Dual-key authorized for STAGING apply only; not a Production GO.",
        )
    return LiveApplyGateVerdict(
        state=LiveApplyGateState.PENDING_HUMAN_AUTHORIZATION,
        is_go_or_approved=False,
        is_production=False,
        dual_key_authorized=False,
        detail="Awaiting dual-key (machine safety + human USER authorization).",
    )


def terminal_state() -> str:
    return LIVE_TERMINAL_STATE
