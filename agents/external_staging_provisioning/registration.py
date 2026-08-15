"""Phase 3.9.13 —— 资源注册框架（T30-T35，PENDING）。

注册动作仅在资源进入 ``PROVISIONED`` 且双钥匙授权后执行；真实资源未提供时，
注册保持 ``NOT_REGISTERED``，不伪造。AI 不代执行注册。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    ResourceProvisioningState,
    ResourceStateMachine,
)


@dataclass
class RegistrationResult:
    resource_id: str
    registered: bool = False
    status: str = "not_registered"
    detail: str = "Real resource pending; no registration performed."

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "registered": self.registered,
            "status": self.status,
            "contains_real_secret": False,
            "detail": self.detail,
        }


class ResourceRegistrar:
    """资源注册器（fail-closed，不伪造注册）。"""

    def attempt_register(
        self, machine: ResourceStateMachine, *, authorized: bool = False
    ) -> RegistrationResult:
        if not authorized:
            return RegistrationResult(
                resource_id=machine.resource_id,
                status="pending_human_authorization",
                detail="注册需双钥匙真人授权；当前未授权，保持未注册。",
            )
        if machine.state is not ResourceProvisioningState.PROVISIONED:
            return RegistrationResult(
                resource_id=machine.resource_id,
                status="blocked_not_provisioned",
                detail="资源未进入 PROVISIONED，注册被拒（不得跳状态）。",
            )
        return RegistrationResult(
            resource_id=machine.resource_id,
            status="authorized_pending_real_register",
            detail="双钥匙授权齐备；真实注册待真人在授权后执行（AI 不代注册）。",
        )


__all__ = ["RegistrationResult", "ResourceRegistrar"]
