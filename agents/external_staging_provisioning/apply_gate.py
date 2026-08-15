"""Phase 3.9.13 —— 双钥匙 Apply Gate（T20）。

状态仅 4 态（**禁** GO / APPROVED / PRODUCTION_READY）：
- ``BLOCKED``
- ``PLAN_ONLY``
- ``PENDING_HUMAN_AUTHORIZATION``
- ``AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY``

裁决：安全校验失败 → BLOCKED；缺 Human Authorization Key → PENDING_HUMAN_AUTHORIZATION；
双钥匙齐备 → AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY；否则 PLAN_ONLY。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_provisioning.authorization_registry import (
    ProvisioningAuthorizationRegistry,
)


class ApplyGateStatus(str, Enum):
    """Apply Gate 状态（4 态，禁 GO/APPROVED/PRODUCTION_READY）。"""

    BLOCKED = "blocked"
    PLAN_ONLY = "plan_only"
    PENDING_HUMAN_AUTHORIZATION = "pending_human_authorization"
    AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY = "authorized_for_external_staging_apply"

    @property
    def is_go_or_approved(self) -> bool:
        return False


@dataclass
class ApplyGateResult:
    status: ApplyGateStatus
    checks: tuple[str, ...] = field(default_factory=tuple)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_go_or_approved": False,
            "checks": list(self.checks),
            "detail": self.detail,
        }


class ExternalStagingProvisioningApplyGate:
    """双钥匙 Apply Gate（fail-closed 评估器）。"""

    def evaluate(
        self,
        *,
        registry: ProvisioningAuthorizationRegistry,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
    ) -> ApplyGateResult:
        checks: list[str] = []

        if not security_ok:
            return ApplyGateResult(
                status=ApplyGateStatus.BLOCKED,
                checks=tuple(checks + ["security_check"]),
                detail="安全校验失败（凭据/契约/环境身份），BLOCKED。",
            )
        checks.append("security_ok")
        if not regression_ok:
            return ApplyGateResult(
                status=ApplyGateStatus.BLOCKED,
                checks=tuple(checks + ["regression_check"]),
                detail="回归测试失败，BLOCKED。",
            )
        checks.append("regression_ok")
        if not repo_clean:
            return ApplyGateResult(
                status=ApplyGateStatus.BLOCKED,
                checks=tuple(checks + ["repo_clean_check"]),
                detail="工作树不干净，BLOCKED。",
            )
        checks.append("repo_clean")

        if not registry.machine_key_present():
            return ApplyGateResult(
                status=ApplyGateStatus.PENDING_HUMAN_AUTHORIZATION,
                checks=tuple(checks + ["machine_key_missing"]),
                detail="Machine Safety Key 缺失，等待真人授权（PENDING_HUMAN_AUTHORIZATION）。",
            )
        if not registry.human_key_present():
            return ApplyGateResult(
                status=ApplyGateStatus.PENDING_HUMAN_AUTHORIZATION,
                checks=tuple(checks + ["human_key_missing"]),
                detail="Human Authorization Key 缺失，等待真人授权（PENDING_HUMAN_AUTHORIZATION）。",
            )
        return ApplyGateResult(
            status=ApplyGateStatus.AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY,
            checks=tuple(checks + ["dual_key_present"]),
            detail="双钥匙齐备，AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY（仍非 GO/PRODUCTION）。",
        )


__all__ = [
    "ApplyGateStatus",
    "ApplyGateResult",
    "ExternalStagingProvisioningApplyGate",
]
