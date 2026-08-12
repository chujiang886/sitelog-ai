"""Phase 3.9.4 OpenTelemetry 遥测适配器（T5）。

- 支持 trace / span / service metadata。
- 建立 Trace ID 与 Governance Traceability / Release ID / Incident ID 的 correlation
  contract（T5）。
- 真实 collector：pending_verification；未配置 → fail-closed（NOT_CONFIGURED）。
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


class OpenTelemetryAdapter(TelemetryProvider):
    """OpenTelemetry 遥测适配器（T5）。"""

    kind = ProviderKind.OPENTELEMETRY
    capabilities = [ProviderCapability.TRACES, ProviderCapability.HEALTH]

    def __init__(
        self,
        *,
        collector_url: Optional[str] = None,
        fixture: Optional[Dict[str, Any]] = None,
        org_id: str = "",
    ) -> None:
        self._collector_url = collector_url
        self._fixture = fixture or {}
        self._org_id = org_id
        self._provider_id = "opentelemetry"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def is_configured(self) -> bool:
        return bool(self._collector_url)

    @staticmethod
    def parse_trace_response(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 OTLP 风格 trace 响应为归一化记录（契约方法，供 fixture 测试）。

        输入形如::

            {"resourceSpans":[{"resource":{"service.name":"backend"},
             "scopeSpans":[{"spans":[{"traceId":"abc","spanId":"d","name":"req",
              "status":{"code":"ERROR"}}]}]}]}

        返回 ``[{"trace_id","service","spans":[{"name","error"}]}]``。
        """
        out: List[Dict[str, Any]] = []
        if not isinstance(raw, dict):
            return out
        for rs in raw.get("resourceSpans", []) or []:
            svc = (rs.get("resource") or {}).get("service.name", "unknown")
            for ss in rs.get("scopeSpans", []) or []:
                for span in ss.get("spans", []) or []:
                    out.append(
                        {
                            "trace_id": span.get("traceId", ""),
                            "service": svc,
                            "spans": [
                                {
                                    "name": span.get("name", ""),
                                    "error": (span.get("status") or {}).get("code") == "ERROR",
                                }
                            ],
                        }
                    )
        return out

    def query_traces(
        self, *, organization_id: str, component: str, limit: int = 50
    ) -> List[TelemetryEnvelope]:
        if not self.is_configured():
            return []
        records = self.parse_trace_response(self._fixture)
        envelopes: List[TelemetryEnvelope] = []
        for rec in records[:limit]:
            envelopes.append(
                self._envelope(
                    telemetry_type=TelemetryType.TRACE,
                    organization_id=organization_id,
                    component=component,
                    timestamp=_now(),
                    payload={
                        "trace_id": rec["trace_id"],
                        "service": rec["service"],
                        "spans": rec["spans"],
                        "source": "opentelemetry",
                    },
                    simulation_only=False,
                    trace_id=rec["trace_id"],
                    integrity_status=IntegrityStatus.UNVERIFIED,
                )
            )
        return envelopes

    def query_metrics(
        self, *, organization_id: str, component: str, window: str = "5m"
    ) -> List[TelemetryEnvelope]:
        return []

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
                payload={"status": "unknown", "detail": "otel collector health (pending_verification)"},
                simulation_only=False,
                integrity_status=IntegrityStatus.UNVERIFIED,
            )
        ]

    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
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
                detail="opentelemetry collector not configured (fail-closed)",
                simulation_only=False,
            )
        return TelemetryProviderHealth(
            provider_id=self._provider_id,
            kind=self.kind,
            status=ProviderStatus.CONFIGURED,
            checked_at=_now(),
            capabilities=self.capabilities,
            detail="otel collector configured; real correlation pending_verification",
            simulation_only=False,
        )


__all__ = ["OpenTelemetryAdapter"]
