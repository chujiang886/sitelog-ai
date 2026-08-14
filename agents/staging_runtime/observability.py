"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Observability（Task 17-21）。

覆盖本地预生产运行时可观测性的**形态描述**（Task 17 健康检查 / 18 遥测 / 19 指标 /
20 日志 / 21 链路追踪）：

- 全部为**描述型**，系统不连接、不采集、不推送真实数据；
- 所有描述标记 ``target=local_staging``、``non_production=True``；
- 拒绝任何把 staging 可观测性伪装为 production 的诉求（fail-closed）。

真实遥测/指标接入由人工在授权后执行；本模块只产出证据形态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingObservabilityError(Exception):
    """Staging 可观测性形态违例（fail-closed）。"""


@dataclass(frozen=True)
class HealthCheckDescriptor:
    name: str
    target: str = "local_staging"
    non_production: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "target": self.target, "non_production": self.non_production}


@dataclass(frozen=True)
class TelemetryDescriptor:
    category: str  # metrics | logs | trace | telemetry
    target: str = "local_staging"
    non_production: bool = True
    collects_real_data: bool = False  # 永远 False：本模块不采集真实数据

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "target": self.target,
            "non_production": self.non_production,
            "collects_real_data": self.collects_real_data,
        }


class StagingRuntimeHealth:
    """本地预生产健康检查形态（Task 17，描述型）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def describe_checks(self) -> tuple[HealthCheckDescriptor, ...]:
        return (
            HealthCheckDescriptor(name="staging_api_health"),
            HealthCheckDescriptor(name="staging_db_connectivity"),
            HealthCheckDescriptor(name="staging_cache_connectivity"),
            HealthCheckDescriptor(name="staging_isolation_guard"),
        )


class StagingTelemetry:
    """本地预生产遥测/指标/日志/链路形态（Task 18-21，描述型）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def describe_collections(self) -> tuple[TelemetryDescriptor, ...]:
        return (
            TelemetryDescriptor(category="metrics"),
            TelemetryDescriptor(category="logs"),
            TelemetryDescriptor(category="trace"),
            TelemetryDescriptor(category="telemetry"),
        )

    def to_manifest(self) -> dict[str, Any]:
        health = StagingRuntimeHealth(self._identity).describe_checks()
        telemetry = self.describe_collections()
        return {
            "environment": self._identity.kind.value,
            "is_production": self._identity.kind.is_production,
            "non_production_bound": self._identity.kind
            in (RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING),
            "health_checks": [c.to_dict() for c in health],
            "telemetry": [t.to_dict() for t in telemetry],
            "collects_real_data": False,
            "note": "形态描述，不连接/不采集/不推送真实数据；真实接入由人工授权后执行。",
        }


__all__ = [
    "StagingObservabilityError",
    "HealthCheckDescriptor",
    "TelemetryDescriptor",
    "StagingRuntimeHealth",
    "StagingTelemetry",
]
