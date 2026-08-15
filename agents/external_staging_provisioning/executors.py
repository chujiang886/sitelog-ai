"""Phase 3.9.13 —— 8 资源执行器（T5-T12, T21-T29）。

每个执行器对应一类资源，封装状态机跃迁。所有真实供给动作（PROVISIONING 及之后）
**必须**经双钥匙 Apply Gate 授权；未授权时执行器仅停留在安全态，绝不跳状态、绝不伪造。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_provisioning.apply_gate import (
    ApplyGateStatus,
    ExternalStagingProvisioningApplyGate,
)
from agents.external_staging_provisioning.authorization_registry import (
    ProvisioningAuthorizationRegistry,
)
from agents.external_staging_provisioning.resource_state_machine import (
    ProvisioningStateRegistry,
    ResourceProvisioningState,
    ResourceStateMachine,
)


class ProvisioningExecutor:
    """单资源执行器（fail-closed）。"""

    def __init__(
        self,
        machine: ResourceStateMachine,
        registry: ProvisioningAuthorizationRegistry,
        apply_gate: ExternalStagingProvisioningApplyGate,
    ) -> None:
        self.machine = machine
        self.registry = registry
        self.apply_gate = apply_gate

    def receive_input(self, *, note: str = "") -> None:
        self.machine.transition_to(
            ResourceProvisioningState.INPUT_RECEIVED, event="receive_input", note=note
        )

    def validate_reference(self, *, note: str = "") -> None:
        self.machine.transition_to(
            ResourceProvisioningState.REFERENCE_VALIDATED,
            event="validate_reference", note=note,
        )

    def build_plan(self, *, note: str = "") -> None:
        self.machine.transition_to(
            ResourceProvisioningState.PLAN_READY, event="build_plan", note=note
        )

    def validate_plan(self, *, note: str = "") -> None:
        self.machine.transition_to(
            ResourceProvisioningState.PLAN_VALIDATED, event="validate_plan", note=note
        )

    def request_human_authorization(self, *, note: str = "") -> None:
        self.machine.transition_to(
            ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING,
            event="request_human_authorization", note=note,
        )

    def attempt_apply(self, *, note: str = "") -> ApplyGateStatus:
        """尝试进入真实 apply。fail-closed：仅当双钥匙授权后允许推进到
        ``AUTHORIZED_FOR_STAGING_APPLY``；真实 PROVISIONING 仍由真人在授权后执行
        （AI 不代执行，绝不伪造 PROVISIONED）。"""

        result = self.apply_gate.evaluate(registry=self.registry)
        if result.status is not ApplyGateStatus.AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY:
            return result.status
        self.machine.transition_to(
            ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY,
            event="authorized_for_staging_apply",
            note=note or "dual-key authorized; real provisioning awaits human",
        )
        return result.status


class ProvisioningExecutorSet:
    """8 资源执行器集合。"""

    def __init__(
        self,
        state_registry: ProvisioningStateRegistry,
        authorization_registry: ProvisioningAuthorizationRegistry,
        apply_gate: ExternalStagingProvisioningApplyGate,
    ) -> None:
        self.executors = {
            rid: ProvisioningExecutor(m, authorization_registry, apply_gate)
            for rid, m in state_registry._machines.items()
        }

    def get(self, resource_id: str) -> ProvisioningExecutor:
        return self.executors[resource_id]


__all__ = ["ProvisioningExecutor", "ProvisioningExecutorSet"]
