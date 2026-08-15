"""Phase 3.9.13 —— 隔离验证框架（T30-T35，NOT VERIFIED）。

隔离验证（网络/租户隔离断言）仅在连通验证通过后执行；真实资源未提供时，
隔离保持 ``NOT_VERIFIED``，不伪造。AI 不执行真实隔离断言。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    ResourceProvisioningState,
    ResourceStateMachine,
)


@dataclass
class IsolationResult:
    resource_id: str
    verified: bool = False
    status: str = "not_verified"
    detail: str = "Real resource pending; no isolation assertion performed."

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "verified": self.verified,
            "status": self.status,
            "contains_real_secret": False,
            "detail": self.detail,
        }


class IsolationVerifier:
    """隔离验证器（fail-closed，不伪造隔离）。"""

    def attempt_verify(
        self, machine: ResourceStateMachine, *, authorized: bool = False
    ) -> IsolationResult:
        if not authorized:
            return IsolationResult(
                resource_id=machine.resource_id,
                status="pending_human_authorization",
                detail="隔离验证需双钥匙真人授权；当前未授权，保持未验证。",
            )
        if machine.state is not ResourceProvisioningState.CONNECTIVITY_VERIFIED:
            return IsolationResult(
                resource_id=machine.resource_id,
                status="blocked_not_connectivity_verified",
                detail="资源未进入 CONNECTIVITY_VERIFIED，隔离验证被拒（不得跳状态）。",
            )
        return IsolationResult(
            resource_id=machine.resource_id,
            status="authorized_pending_real_isolation",
            detail="双钥匙授权齐备；真实隔离验证待真人在授权后执行（AI 不执行真实隔离断言）。",
        )


__all__ = ["IsolationResult", "IsolationVerifier"]
