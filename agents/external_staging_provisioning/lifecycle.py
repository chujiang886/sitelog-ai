"""Phase 3.9.13 —— 资源生命周期处理（rollback / reconciliation / failure，T36-T40）。

- rollback：回退一态（仅到允许的前驱，fail-closed）。
- reconcile：实际态 vs 期望态对账。
- handle_failure：转入失败态（仅当失败态合法）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    FAILURE_STATES,
    ResourceProvisioningState,
    ResourceStateMachine,
    ResourceStateMachineError,
)


class LifecycleError(ValueError):
    """生命周期处理违例。"""


_PREDECESSORS: dict[ResourceProvisioningState, ResourceProvisioningState | None] = {
    ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE: None,
    ResourceProvisioningState.INPUT_RECEIVED: (
        ResourceProvisioningState.PENDING_EXTERNAL_STAGING_RESOURCE
    ),
    ResourceProvisioningState.REFERENCE_VALIDATED: (
        ResourceProvisioningState.INPUT_RECEIVED
    ),
    ResourceProvisioningState.PLAN_READY: ResourceProvisioningState.REFERENCE_VALIDATED,
    ResourceProvisioningState.PLAN_VALIDATED: ResourceProvisioningState.PLAN_READY,
    ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING: (
        ResourceProvisioningState.PLAN_VALIDATED
    ),
    ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY: (
        ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING
    ),
    ResourceProvisioningState.PROVISIONING: (
        ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY
    ),
    ResourceProvisioningState.PROVISIONED: ResourceProvisioningState.PROVISIONING,
    ResourceProvisioningState.REGISTERED: ResourceProvisioningState.PROVISIONED,
    ResourceProvisioningState.CONNECTIVITY_VERIFIED: (
        ResourceProvisioningState.REGISTERED
    ),
    ResourceProvisioningState.ISOLATION_VERIFIED: (
        ResourceProvisioningState.CONNECTIVITY_VERIFIED
    ),
    ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING: (
        ResourceProvisioningState.ISOLATION_VERIFIED
    ),
}


def rollback(machine: ResourceStateMachine, *, reason: str = "") -> None:
    """回退一态（fail-closed）。"""

    if machine.state in FAILURE_STATES:
        raise LifecycleError(
            f"资源 {machine.resource_id} 处于失败态，需先 resolve 再回退。"
        )
    pred = _PREDECESSORS.get(machine.state)
    if pred is None:
        raise LifecycleError(f"资源 {machine.resource_id} 已处于初始态，无法回退。")
    machine.state = pred
    machine.last_event = "rollback"
    if reason:
        machine.notes = machine.notes + (f"rollback: {reason}",)


def handle_failure(
    machine: ResourceStateMachine,
    failure: ResourceProvisioningState,
    *,
    reason: str = "",
) -> None:
    """转入失败态（仅当失败态合法，且为合法前驱跃迁）。"""

    if failure not in FAILURE_STATES:
        raise LifecycleError(f"{failure.value} 非合法失败态。")
    machine.transition_to(failure, event="failure", note=reason)


def reconcile(
    registry: Any, expected: dict[str, ResourceProvisioningState]
) -> dict[str, Any]:
    """实际态 vs 期望态对账。"""

    mismatches: list[dict[str, Any]] = []
    for rid, exp in expected.items():
        try:
            actual = registry.get(rid).state
        except ResourceStateMachineError:
            mismatches.append({"resource_id": rid, "error": "unknown_resource"})
            continue
        if actual is not exp:
            mismatches.append({
                "resource_id": rid,
                "expected": exp.value,
                "actual": actual.value,
            })
    return {
        "total": len(expected),
        "mismatches": mismatches,
        "in_sync": len(mismatches) == 0,
    }


__all__ = ["LifecycleError", "rollback", "handle_failure", "reconcile"]
