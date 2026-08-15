"""Phase 3.9.10 —— Runtime Qualification（Task 17）。

验证 External Staging 运行时健康：

- backend / frontend / DB / IdP / storage / audit / governance / release /
  change-control / LLM / voice / telemetry / alerting。

状态仅限：``HEALTHY`` / ``DEGRADED`` / ``UNHEALTHY`` / ``UNKNOWN`` / ``NOT_CONFIGURED``。
**``UNKNOWN`` 不得等同 ``HEALTHY``**（fail-closed）。

基线（无真实 External 运行时接入）全部 ``NOT_CONFIGURED`` / ``UNKNOWN``，
绝不声称 ``HEALTHY``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.models import RuntimeHealthStatus

# 受监控的运行时组件（顺序稳定，供契约/契约测试）。
RUNTIME_COMPONENTS: tuple[str, ...] = (
    "backend",
    "frontend",
    "database",
    "identity_provider",
    "object_storage",
    "audit",
    "governance",
    "release",
    "change_control",
    "llm",
    "voice",
    "telemetry",
    "alerting",
)


@dataclass
class ComponentHealth:
    """单组件健康。"""

    component: str
    status: RuntimeHealthStatus
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.value,
            "healthy": self.status.is_healthy,
            "detail": self.detail,
        }


@dataclass
class RuntimeHealthReport:
    """整体运行时健康报告。"""

    components: tuple[ComponentHealth, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, Any]:
        healthy = sum(1 for c in self.components if c.status.is_healthy)
        unknown = sum(1 for c in self.components if c.status is RuntimeHealthStatus.UNKNOWN)
        not_configured = sum(
            1 for c in self.components if c.status is RuntimeHealthStatus.NOT_CONFIGURED
        )
        return {
            "total": len(self.components),
            "healthy": healthy,
            "unknown": unknown,
            "not_configured": not_configured,
            "all_healthy": healthy == len(self.components) and len(self.components) > 0,
            # UNKNOWN 不计入 healthy（fail-closed）
            "unknown_treated_as_healthy": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "components": [c.to_dict() for c in self.components],
            "summary": self.summary(),
        }


class RuntimeQualification:
    """运行时资格验证（只读评估，不执行动作）。"""

    def evaluate(
        self,
        *,
        overrides: dict[str, RuntimeHealthStatus] | None = None,
    ) -> RuntimeHealthReport:
        """评估各组件健康。``overrides`` 仅用于 contract 测试注入确定值。

        fail-closed：未提供真实证据的组件一律 ``NOT_CONFIGURED`` / ``UNKNOWN``，
        不得默认 ``HEALTHY``。
        """

        overrides = overrides or {}
        components: list[ComponentHealth] = []
        for name in RUNTIME_COMPONENTS:
            status = overrides.get(name, RuntimeHealthStatus.NOT_CONFIGURED)
            # 防御：UNKNOWN 永远不能被判为 HEALTHY
            if status is RuntimeHealthStatus.UNKNOWN:
                detail = "未获得真实运行证据（UNKNOWN，不视作 HEALTHY）。"
            elif status is RuntimeHealthStatus.NOT_CONFIGURED:
                detail = "外部预生产运行时未接入（NOT_CONFIGURED）。"
            else:
                detail = "已登记状态（来自 overrides/真实证据）。"
            components.append(ComponentHealth(name, status, detail))
        return RuntimeHealthReport(components=tuple(components))


__all__ = [
    "RUNTIME_COMPONENTS",
    "ComponentHealth",
    "RuntimeHealthReport",
    "RuntimeQualification",
]
