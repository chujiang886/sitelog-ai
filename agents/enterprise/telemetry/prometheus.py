"""Phase 3.9.4 Prometheus 遥测适配器（T4）。

- 完成 Provider 端口、查询模型、响应解析、错误处理、配置校验。
- 未配置真实 Prometheus endpoint → fail-closed（``NOT_CONFIGURED``），**绝不**自动降级
  为 Synthetic 并伪装成 production（红线⑪）。
- 真实 HTTP 拉取不在本阶段执行（无真实 endpoint）；使用 fixture / mocked 响应验证契约。
  真实 endpoint 一律 ``pending_verification``。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.telemetry.models import (
    IntegrityStatus,
    ProviderCapability,
    ProviderKind,
    ProviderStatus,
    TelemetryEnvelope,
    TelemetryProviderHealth,
    TelemetryType,
)
from agents.enterprise.telemetry.provider import TelemetryProvider


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrometheusTelemetryAdapter(TelemetryProvider):
    """Prometheus 遥测适配器（T4）。"""

    kind = ProviderKind.PROMETHEUS
    capabilities = [ProviderCapability.METRICS, ProviderCapability.HEALTH]

    def __init__(
        self,
        *,
        prometheus_url: Optional[str] = None,
        fixture: Optional[Dict[str, Any]] = None,
        org_id: str = "",
    ) -> None:
        self._prometheus_url = prometheus_url
        self._fixture = fixture or {}
        self._org_id = org_id
        self._provider_id = "prometheus"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def is_configured(self) -> bool:
        return bool(self._prometheus_url)

    @staticmethod
    def parse_query_response(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 Prometheus instant query 响应为归一化指标记录（契约方法，供 fixture 测试）。

        输入形如::

            {"status":"success","data":{"resultType":"vector",
             "result":[{"metric":{"__name__":"up","instance":"x"},"value":[1700000000,"1"]}]}}

        返回 ``[{"name":..., "labels":..., "value": float, "timestamp":...}, ...]``。
        """
        out: List[Dict[str, Any]] = []
        if not isinstance(raw, dict):
            return out
        data = raw.get("data") or {}
        if data.get("resultType") != "vector":
            return out
        for item in data.get("result", []) or []:
            metric = item.get("metric", {}) or {}
            value_pair = item.get("value") or [None, None]
            ts, val = value_pair[0], value_pair[1]
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "name": metric.get("__name__", "unknown"),
                    "labels": {k: v for k, v in metric.items() if k != "__name__"},
                    "value": num,
                    "timestamp": ts,
                }
            )
        return out

    def query_metrics(
        self, *, organization_id: str, component: str, window: str = "5m"
    ) -> List[TelemetryEnvelope]:
        # 红线⑪：未配置真实 endpoint → fail-closed 返回空，绝不伪造 / 降级为 Synthetic。
        if not self.is_configured():
            return []
        records = self.parse_query_response(self._fixture)
        envelopes: List[TelemetryEnvelope] = []
        for rec in records:
            envelopes.append(
                self._envelope(
                    telemetry_type=TelemetryType.METRIC,
                    organization_id=organization_id,
                    component=component,
                    timestamp=_now(),
                    payload={
                        "window": window,
                        "metric": rec["name"],
                        "labels": rec["labels"],
                        "value": rec["value"],
                        "source": "prometheus",
                    },
                    simulation_only=False,  # 真实源（若配置），但真实连接 pending_verification
                    integrity_status=IntegrityStatus.UNVERIFIED,
                )
            )
        return envelopes

    def query_health(
        self, *, organization_id: str, component: str
    ) -> List[TelemetryEnvelope]:
        if not self.is_configured():
            return []
        return [
            self._envelope(
                telemetry_type=TelemetryType.HEALTH,
                organization_id=organization_id,
                component=component,
                timestamp=_now(),
                payload={"status": "unknown", "detail": "prometheus health via up metric (pending_verification)"},
                simulation_only=False,
                integrity_status=IntegrityStatus.UNVERIFIED,
            )
        ]

    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
    ) -> List[TelemetryEnvelope]:
        # Prometheus 非日志源；未配置 → 空。
        return []

    def query_traces(
        self, *, organization_id: str, component: str, limit: int = 50
    ) -> List[TelemetryEnvelope]:
        return []

    def provider_health(self) -> TelemetryProviderHealth:
        if not self.is_configured():
            return TelemetryProviderHealth(
                provider_id=self._provider_id,
                kind=self.kind,
                status=ProviderStatus.NOT_CONFIGURED,
                checked_at=_now(),
                capabilities=self.capabilities,
                detail="prometheus endpoint not configured (fail-closed)",
                simulation_only=False,
            )
        return TelemetryProviderHealth(
            provider_id=self._provider_id,
            kind=self.kind,
            status=ProviderStatus.CONFIGURED,
            checked_at=_now(),
            capabilities=self.capabilities,
            detail="prometheus configured; live connectivity pending_verification (no real fetch in this phase)",
            simulation_only=False,
        )


__all__ = ["PrometheusTelemetryAdapter"]
