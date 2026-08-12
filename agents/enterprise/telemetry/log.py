"""Phase 3.9.4 日志遥测 Provider / Adapter（T6）。

- 统一日志端口，未来兼容 Loki / Elasticsearch / OpenSearch。
- 至少完成：统一接口 + Synthetic 实现 + 一个 HTTP Adapter 契约。
- 禁止绑定单一供应商（backend 可配 loki / elasticsearch / opensearch）。
- 未配置真实 endpoint → fail-closed（NOT_CONFIGURED）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.telemetry.models import (
    IntegrityStatus,
    ProviderCapability,
    ProviderKind,
    ProviderStatus,
    SyntheticFaultScenario,
    TelemetryEnvelope,
    TelemetryProviderHealth,
    TelemetryType,
)
from agents.enterprise.telemetry.provider import TelemetryProvider


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# 场景 → 日志级别 / 消息（合成 fixture）。
_SCENARIO_LOG: Dict[str, Dict[str, str]] = {
    SyntheticFaultScenario.HEALTHY.value: {"level": "INFO", "message": "service nominal"},
    SyntheticFaultScenario.IDENTITY_AUTH_FAILURE.value: {"level": "WARN", "message": "identity auth failed"},
    SyntheticFaultScenario.PERMISSION_DENIAL_SPIKE.value: {"level": "WARN", "message": "permission denied spike"},
    SyntheticFaultScenario.BACKEND_ERROR_SPIKE.value: {"level": "ERROR", "message": "backend 500 spike"},
    SyntheticFaultScenario.DATABASE_UNAVAILABLE.value: {"level": "ERROR", "message": "db connection refused"},
    SyntheticFaultScenario.LLM_TIMEOUT.value: {"level": "ERROR", "message": "llm request timeout"},
    SyntheticFaultScenario.ASR_UNAVAILABLE.value: {"level": "ERROR", "message": "asr unavailable"},
    SyntheticFaultScenario.TTS_UNAVAILABLE.value: {"level": "ERROR", "message": "tts unavailable"},
    SyntheticFaultScenario.RELEASE_REGRESSION.value: {"level": "WARN", "message": "release regression detected"},
    SyntheticFaultScenario.AUDIT_UNAVAILABLE.value: {"level": "ERROR", "message": "audit write timeout"},
    SyntheticFaultScenario.GOVERNANCE_BACKLOG.value: {"level": "WARN", "message": "governance backlog growing"},
    SyntheticFaultScenario.BACKEND_LATENCY.value: {"level": "WARN", "message": "backend p99 latency high"},
}


class SyntheticLogProvider(TelemetryProvider):
    """合成日志 Provider（T6）。simulation_only=True。"""

    kind = ProviderKind.SYNTHETIC
    capabilities = [ProviderCapability.LOGS]

    def __init__(
        self, *, provider_id: str = "synthetic-log", scenario: SyntheticFaultScenario = SyntheticFaultScenario.HEALTHY
    ) -> None:
        self._provider_id = provider_id
        self._scenario = scenario

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def is_configured(self) -> bool:
        return True

    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
    ) -> List[TelemetryEnvelope]:
        spec = _SCENARIO_LOG.get(self._scenario.value, _SCENARIO_LOG["healthy"])
        return [
            self._envelope(
                telemetry_type=TelemetryType.LOG,
                organization_id=organization_id,
                component=component,
                timestamp=_now(),
                payload={"level": spec["level"], "message": spec["message"], "scenario": self._scenario.value},
                simulation_only=True,
                integrity_status=IntegrityStatus.INTACT,
            )
        ]

    def query_metrics(self, *, organization_id: str, component: str, window: str = "5m") -> List[TelemetryEnvelope]:
        return []

    def query_health(self, *, organization_id: str, component: str) -> List[TelemetryEnvelope]:
        return []

    def query_traces(self, *, organization_id: str, component: str, limit: int = 50) -> List[TelemetryEnvelope]:
        return []

    def provider_health(self) -> TelemetryProviderHealth:
        return TelemetryProviderHealth(
            provider_id=self._provider_id,
            kind=self.kind,
            status=ProviderStatus.CONFIGURED,
            checked_at=_now(),
            capabilities=self.capabilities,
            detail="synthetic log source; envelopes simulation_only=True",
            simulation_only=True,
        )


class LogHttpAdapter(TelemetryProvider):
    """日志 HTTP Adapter 契约（T6）。兼容 Loki / Elasticsearch / OpenSearch。

    未配置真实 endpoint → fail-closed（NOT_CONFIGURED），绝不伪造。真实 endpoint
    pending_verification。
    """

    capabilities = [ProviderCapability.LOGS]

    _BACKEND_KIND = {
        "loki": ProviderKind.LOKI,
        "elasticsearch": ProviderKind.ELASTICSEARCH,
        "opensearch": ProviderKind.OPENSEARCH,
    }

    def __init__(
        self,
        *,
        backend: str = "loki",
        endpoint: Optional[str] = None,
        fixture: Optional[Dict[str, Any]] = None,
        org_id: str = "",
    ) -> None:
        self._backend = backend
        self._endpoint = endpoint
        self._fixture = fixture or {}
        self._org_id = org_id
        self._provider_id = f"log-{backend}"
        self.kind = self._BACKEND_KIND.get(backend, ProviderKind.UNKNOWN)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def is_configured(self) -> bool:
        return bool(self._endpoint)

    @staticmethod
    def parse_log_response(raw: Dict[str, Any], backend: str = "loki") -> List[Dict[str, Any]]:
        """解析日志后端响应为归一化记录（契约方法，供 fixture 测试）。

        Loki 形如 ``{"data":{"result":[{"stream":{...},"values":[["1700000000000000000","msg"]]}]}}``；
        ES/OpenSearch 形如 ``{"hits":{"hits":[{"_source":{"@timestamp":...,"message":...,"level":...}}]}}``。
        """
        out: List[Dict[str, Any]] = []
        if not isinstance(raw, dict):
            return out
        if backend == "loki":
            for res in (raw.get("data") or {}).get("result", []) or []:
                stream = res.get("stream", {}) or {}
                for ts, msg in res.get("values", []) or []:
                    out.append({"timestamp": ts, "message": msg, "level": stream.get("level", "INFO"), "component": stream.get("component", "unknown")})
        else:
            for hit in ((raw.get("hits") or {}).get("hits", []) or []):
                src = hit.get("_source", {}) or {}
                out.append(
                    {
                        "timestamp": src.get("@timestamp", ""),
                        "message": src.get("message", ""),
                        "level": src.get("level", "INFO"),
                        "component": src.get("component", "unknown"),
                    }
                )
        return out

    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
    ) -> List[TelemetryEnvelope]:
        if not self.is_configured():
            return []
        records = self.parse_log_response(self._fixture, self._backend)[:limit]
        envelopes: List[TelemetryEnvelope] = []
        for rec in records:
            envelopes.append(
                self._envelope(
                    telemetry_type=TelemetryType.LOG,
                    organization_id=organization_id,
                    component=rec.get("component", component),
                    timestamp=_now(),
                    payload={"level": rec.get("level", "INFO"), "message": rec.get("message", ""), "source": self._backend},
                    simulation_only=False,
                    integrity_status=IntegrityStatus.UNVERIFIED,
                )
            )
        return envelopes

    def query_metrics(self, *, organization_id: str, component: str, window: str = "5m") -> List[TelemetryEnvelope]:
        return []

    def query_health(self, *, organization_id: str, component: str) -> List[TelemetryEnvelope]:
        return []

    def query_traces(self, *, organization_id: str, component: str, limit: int = 50) -> List[TelemetryEnvelope]:
        return []

    def provider_health(self) -> TelemetryProviderHealth:
        if not self.is_configured():
            return TelemetryProviderHealth(
                provider_id=self._provider_id,
                kind=self.kind,
                status=ProviderStatus.NOT_CONFIGURED,
                checked_at=_now(),
                capabilities=self.capabilities,
                detail=f"{self._backend} log endpoint not configured (fail-closed)",
                simulation_only=False,
            )
        return TelemetryProviderHealth(
            provider_id=self._provider_id,
            kind=self.kind,
            status=ProviderStatus.CONFIGURED,
            checked_at=_now(),
            capabilities=self.capabilities,
            detail=f"{self._backend} configured; live connectivity pending_verification",
            simulation_only=False,
        )


__all__ = ["SyntheticLogProvider", "LogHttpAdapter"]
