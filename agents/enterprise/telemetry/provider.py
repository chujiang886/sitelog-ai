"""Phase 3.9.4 遥测 Provider 端口（T1, T7）。

高层 Observability / Telemetry 服务**只依赖此抽象端口**，绝不依赖具体 Prometheus /
OpenTelemetry / Loki SDK。所有具体适配器（Synthetic / Prometheus / OTel / Log）实现该端口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agents.enterprise.telemetry.models import (
    IntegrityStatus,
    ProviderCapability,
    ProviderKind,
    ProviderStatus,
    TelemetryEnvelope,
    TelemetryProviderHealth,
)


class TelemetryProvider(ABC):
    """遥测 Provider 统一端口（T1）。

    高层服务通过 ``query_metrics`` / ``query_health`` / ``query_logs`` / ``query_traces``
    拉取遥测，通过 ``provider_health`` 探活。所有返回以 ``TelemetryEnvelope`` 归一。
    """

    # 子类声明自身类别与能力。
    kind: ProviderKind = ProviderKind.UNKNOWN
    capabilities: List[ProviderCapability] = []

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider 唯一标识。"""

    @abstractmethod
    def is_configured(self) -> bool:
        """是否已配置真实数据源。未配置 → 上层应视为 NOT_CONFIGURED（fail-closed）。"""

    @abstractmethod
    def query_metrics(
        self, *, organization_id: str, component: str, window: str = "5m"
    ) -> List[TelemetryEnvelope]:
        """查询指标遥测。"""

    @abstractmethod
    def query_health(
        self, *, organization_id: str, component: str
    ) -> List[TelemetryEnvelope]:
        """查询健康遥测。"""

    @abstractmethod
    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
    ) -> List[TelemetryEnvelope]:
        """查询日志遥测。"""

    @abstractmethod
    def query_traces(
        self, *, organization_id: str, component: str, limit: int = 50
    ) -> List[TelemetryEnvelope]:
        """查询链路追踪遥测。"""

    @abstractmethod
    def provider_health(self) -> TelemetryProviderHealth:
        """Provider 健康检查（T9）。未配置真实源时返回 NOT_CONFIGURED。"""

    # ---- 通用工具 ----
    def _envelope(
        self,
        *,
        telemetry_type: Any,
        organization_id: str,
        component: str,
        timestamp: str,
        payload: Any,
        simulation_only: bool = False,
        trace_id: str = "",
        release_id: str = "",
        integrity_status: Any = None,
    ) -> TelemetryEnvelope:
        return TelemetryEnvelope(
            provider=self.provider_id,
            telemetry_type=telemetry_type,
            organization_id=organization_id,
            component=component,
            timestamp=timestamp,
            payload=payload,
            simulation_only=simulation_only,
            trace_id=trace_id,
            release_id=release_id,
            integrity_status=integrity_status or IntegrityStatus.UNVERIFIED,
        )

    def capability_set(self) -> List[ProviderCapability]:
        return list(self.capabilities)
