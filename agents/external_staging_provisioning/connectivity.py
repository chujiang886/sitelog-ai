"""Phase 3.9.13 —— 连通性验证框架（T30-T35，NOT VERIFIED）。

连通性验证（真实连接测试）仅在资源注册且授权后执行；真实资源未提供时，
连通性保持 ``NOT_VERIFIED``，不伪造。AI 不发起真实连接。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    ResourceProvisioningState,
    ResourceStateMachine,
)


@dataclass
class ConnectivityResult:
    resource_id: str
    verified: bool = False
    status: str = "not_verified"
    detail: str = "Real resource pending; no connectivity test performed."

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "verified": self.verified,
            "status": self.status,
            "contains_real_secret": False,
            "detail": self.detail,
        }


class ConnectivityVerifier:
    """连通性验证器（fail-closed，不伪造连通）。"""

    def attempt_verify(
        self, machine: ResourceStateMachine, *, authorized: bool = False
    ) -> ConnectivityResult:
        if not authorized:
            return ConnectivityResult(
                resource_id=machine.resource_id,
                status="pending_human_authorization",
                detail="连通验证需双钥匙真人授权；当前未授权，保持未验证。",
            )
        if machine.state is not ResourceProvisioningState.REGISTERED:
            return ConnectivityResult(
                resource_id=machine.resource_id,
                status="blocked_not_registered",
                detail="资源未进入 REGISTERED，连通验证被拒（不得跳状态）。",
            )
        return ConnectivityResult(
            resource_id=machine.resource_id,
            status="authorized_pending_real_connectivity",
            detail="双钥匙授权齐备；真实连通验证待真人在授权后执行（AI 不发起真实连接）。",
        )


__all__ = ["ConnectivityResult", "ConnectivityVerifier"]
