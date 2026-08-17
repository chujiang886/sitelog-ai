"""Phase 3.9.14 —— Runtime Health 健康检查（Task 29，fail-closed）。

``RuntimeHealthHarness`` 描述 External Staging 运行时的**健康形态**：
- 结构性健康检查（来自 ``StagingRuntimeHealth`` 的 4 项 + ``StagingTelemetry`` 遥测形态），
  全部非生产、不连接、不采集真实数据；
- 8 个外部资源的运行时健康**全部 PENDING**（真实外部资源尚未由真人供给，Track B），
  统一标记 ``PENDING_EXTERNAL_STAGING_RESOURCE``，**不阻塞**工程。

整体健康态为 ``PLAN_ONLY``：健康形态已定义且非生产，但真实运行时健康须由真人接入后验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.staging_runtime.observability import StagingTelemetry, StagingRuntimeHealth

from .identity import external_staging_identity
from .runtime_manifest import EXTERNAL_RESOURCE_KINDS  # 复用 8 资源种类

HEALTH_PENDING_STATUS = "PENDING_EXTERNAL_STAGING_RESOURCE"


@dataclass(frozen=True)
class ResourceHealthVerdict:
    """单条外部资源运行时健康结论（fail-closed，plan-only）。"""

    resource: str
    real_resource_present: bool
    status: str  # PENDING_EXTERNAL_STAGING_RESOURCE
    is_production: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "real_resource_present": self.real_resource_present,
            "status": self.status,
            "is_production": self.is_production,
            "detail": self.detail,
        }


@dataclass
class RuntimeHealthReport:
    """Runtime Health 汇总（结构化，机器可读）。"""

    passed: bool
    structural_health_count: int
    external_resources_health_pending: int
    overall_status: str  # PLAN_ONLY
    is_production: bool
    real_apply_allowed: bool
    structural_checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    resource_health: tuple[ResourceHealthVerdict, ...] = field(default_factory=tuple)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "structural_health_count": self.structural_health_count,
            "external_resources_health_pending": self.external_resources_health_pending,
            "overall_status": self.overall_status,
            "is_production": self.is_production,
            "real_apply_allowed": self.real_apply_allowed,
            "structural_checks": list(self.structural_checks),
            "resource_health": [r.to_dict() for r in self.resource_health],
            "generated_at": self.generated_at,
        }


class RuntimeHealthHarness:
    """External Staging 运行时健康形态描述（fail-closed，plan-only）。"""

    def __init__(self, identity=None) -> None:
        self._identity = identity or external_staging_identity()

    def assess(self) -> RuntimeHealthReport:
        # 结构性健康检查（4 项，来自 StagingRuntimeHealth）
        checks = StagingRuntimeHealth(self._identity).describe_checks()
        structural = tuple(c.to_dict() for c in checks)
        # 遥测形态（不采集真实数据）
        telemetry = StagingTelemetry(self._identity).to_manifest()
        all_non_production = all(c["non_production"] for c in structural) and (
            telemetry["is_production"] is False and telemetry["collects_real_data"] is False
        )
        structural_ok = len(structural) == 4 and all_non_production

        # 8 个外部资源的运行时健康：全部 PENDING（真实资源未供给）
        resource_health = tuple(
            ResourceHealthVerdict(
                resource=r,
                real_resource_present=False,
                status=HEALTH_PENDING_STATUS,
                is_production=False,
                detail="真实外部资源尚未由真人供给（Track B）；健康形态已定义且非生产。",
            )
            for r in EXTERNAL_RESOURCE_KINDS
        )

        # 整体：结构健康成立 + 无 production 泄漏，但真实运行时健康待真人接入
        passed = structural_ok and self._identity.kind.is_production is False
        return RuntimeHealthReport(
            passed=passed,
            structural_health_count=len(structural),
            external_resources_health_pending=sum(
                1 for r in resource_health if r.status == HEALTH_PENDING_STATUS
            ),
            overall_status="PLAN_ONLY",
            is_production=self._identity.kind.is_production,
            real_apply_allowed=False,
            structural_checks=structural,
            resource_health=resource_health,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "HEALTH_PENDING_STATUS",
    "ResourceHealthVerdict",
    "RuntimeHealthReport",
    "RuntimeHealthHarness",
]
