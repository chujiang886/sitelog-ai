"""Phase 3.9.13 —— 无伪造 / 红线校验（validator_execution，T41-T45 支撑）。

fail-closed 断言：
- ``engineering_enabled`` 必须为 False（最高红线）。
- 分项进度全 0/8（``any_real_progress`` 必须为 False）。
- Apply Gate 状态**绝不**为 GO/APPROVED。
- ``real_resources_provisioned`` 必须为 0。
- 证据链 ``fabrication_free`` 必须为 True。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.external_staging_provisioning.resource_state_machine import (
    build_default_bom,
    ProvisioningStateRegistry,
)
from agents.external_staging_provisioning.aggregator import (
    PartialProgressAggregator,
)
from agents.external_staging_provisioning.apply_gate import (
    ExternalStagingProvisioningApplyGate,
    ApplyGateStatus,
)
from agents.external_staging_provisioning.authorization_registry import (
    ProvisioningAuthorizationRegistry,
)
from agents.external_staging_provisioning.evidence import EvidenceChain


@dataclass
class ValidationResult:
    passed: bool
    violations: tuple[str, ...]
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": list(self.violations),
            "detail": self.detail,
        }


class ExecutionValidatorError(ValueError):
    """无伪造 / 红线校验失败。"""


def validate_execution_no_fabrication(
    *, real_resources_provisioned: int = 0
) -> ValidationResult:
    """fail-closed 校验零真实资源供给执行的红线与无伪造约束。"""

    violations: list[str] = []

    engineering_enabled = bool(load_engineering_enabled())
    if engineering_enabled is not False:
        violations.append("REDLINE: engineering_enabled must be False")

    reg = ProvisioningStateRegistry(build_default_bom())
    agg = PartialProgressAggregator().aggregate(reg)
    agg_d = agg.to_dict()
    if agg_d["any_real_progress"]:
        violations.append("FABRICATION: any_real_progress must be False (0/8 expected)")
    for k in ("provisioned", "registered", "connected", "isolated", "qualified"):
        if agg_d["counts"][k] != 0:
            violations.append(f"FABRICATION: {k} must be 0, got {agg_d['counts'][k]}")

    auth = ProvisioningAuthorizationRegistry()
    gate = ExternalStagingProvisioningApplyGate().evaluate(
        registry=auth, security_ok=True, regression_ok=True, repo_clean=True,
    )
    if gate.status is ApplyGateStatus.AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY:
        violations.append("REDLINE: apply gate must not reach AUTHORIZED beyond pending human auth in AI-only path")
    if gate.status.is_go_or_approved:
        violations.append("REDLINE: apply gate must never be GO/APPROVED")

    if real_resources_provisioned != 0:
        violations.append("FABRICATION: real_resources_provisioned must be 0")

    ev = EvidenceChain()
    ev.capture_pending(reg)
    if not ev.fabrication_free:
        violations.append("FABRICATION: evidence chain marked non-fabrication-free")

    return ValidationResult(
        passed=len(violations) == 0,
        violations=tuple(violations),
        detail={
            "engineering_enabled": engineering_enabled,
            "aggregator": agg_d,
            "apply_gate_status": gate.status.value,
            "real_resources_provisioned": real_resources_provisioned,
            "fabrication_free": ev.fabrication_free,
        },
    )


__all__ = [
    "ValidationResult",
    "ExecutionValidatorError",
    "validate_execution_no_fabrication",
]
