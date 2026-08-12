"""Phase 3.9.4 合成遥测 Provider / 故障场景 / 故障注入（T3, T9, T10, T11）。

- ``SyntheticTelemetryProvider``：用于单元测试 / 集成测试 / 故障演练 / E2E 验证，生成
  显式 ``simulation_only=True`` 的遥测信封。禁止隐藏该字段（红线⑪）。
- ``SyntheticFaultInjection``：逻辑层故障注入，**只能**注入 ``SyntheticTelemetryProvider``，
  禁止向真实服务注入故障 / kill 进程 / 断真实网络 / 改真实库 / 污染真实配置（红线⑥/⑭）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from agents.enterprise.red_line import EnterpriseRedLineViolationError
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


# 场景 → 组件健康映射（合成，仅 fixture 阈值，禁止写成真实生产阈值）。
_SCENARIO_HEALTH: Dict[str, Dict[str, str]] = {
    SyntheticFaultScenario.HEALTHY.value: {"status": "healthy", "detail": "基线健康"},
    SyntheticFaultScenario.BACKEND_LATENCY.value: {"status": "degraded", "detail": "后端延迟升高"},
    SyntheticFaultScenario.BACKEND_ERROR_SPIKE.value: {"status": "unhealthy", "detail": "后端错误率飙升"},
    SyntheticFaultScenario.DATABASE_UNAVAILABLE.value: {"status": "unhealthy", "detail": "数据库不可用", "component": "database"},
    SyntheticFaultScenario.IDENTITY_AUTH_FAILURE.value: {"status": "degraded", "detail": "身份认证失败", "component": "identity"},
    SyntheticFaultScenario.PERMISSION_DENIAL_SPIKE.value: {"status": "degraded", "detail": "权限拒绝激增", "component": "identity"},
    SyntheticFaultScenario.LLM_TIMEOUT.value: {"status": "unhealthy", "detail": "LLM 超时"},
    SyntheticFaultScenario.ASR_UNAVAILABLE.value: {"status": "unhealthy", "detail": "ASR 不可用", "component": "asr"},
    SyntheticFaultScenario.TTS_UNAVAILABLE.value: {"status": "unhealthy", "detail": "TTS 不可用", "component": "tts"},
    SyntheticFaultScenario.RELEASE_REGRESSION.value: {"status": "degraded", "detail": "发布回归", "component": "release_gate"},
    SyntheticFaultScenario.AUDIT_UNAVAILABLE.value: {"status": "unhealthy", "detail": "审计服务不可用", "component": "audit"},
    SyntheticFaultScenario.GOVERNANCE_BACKLOG.value: {"status": "degraded", "detail": "治理积压", "component": "governance_workflow"},
}

# 场景 → 指标异常（合成 fixture 数值）。
_SCENARIO_METRICS: Dict[str, Dict[str, float]] = {
    SyntheticFaultScenario.HEALTHY.value: {"availability_ratio": 0.999, "error_rate": 0.001, "p99_latency_ms": 120.0},
    SyntheticFaultScenario.BACKEND_LATENCY.value: {"availability_ratio": 0.998, "error_rate": 0.004, "p99_latency_ms": 1850.0},
    SyntheticFaultScenario.BACKEND_ERROR_SPIKE.value: {"availability_ratio": 0.912, "error_rate": 0.088, "p99_latency_ms": 2400.0},
    SyntheticFaultScenario.DATABASE_UNAVAILABLE.value: {"availability_ratio": 0.840, "error_rate": 0.160, "p99_latency_ms": 3000.0},
    SyntheticFaultScenario.IDENTITY_AUTH_FAILURE.value: {"availability_ratio": 0.970, "error_rate": 0.030, "auth_failure_ratio": 0.22},
    SyntheticFaultScenario.PERMISSION_DENIAL_SPIKE.value: {"availability_ratio": 0.980, "error_rate": 0.020, "permission_denial_ratio": 0.18},
    SyntheticFaultScenario.LLM_TIMEOUT.value: {"availability_ratio": 0.960, "error_rate": 0.040, "llm_timeout_ratio": 0.31},
    SyntheticFaultScenario.ASR_UNAVAILABLE.value: {"availability_ratio": 0.950, "error_rate": 0.050, "asr_error_ratio": 0.40},
    SyntheticFaultScenario.TTS_UNAVAILABLE.value: {"availability_ratio": 0.950, "error_rate": 0.050, "tts_error_ratio": 0.40},
    SyntheticFaultScenario.RELEASE_REGRESSION.value: {"availability_ratio": 0.965, "error_rate": 0.035, "regression_score": 0.27},
    SyntheticFaultScenario.AUDIT_UNAVAILABLE.value: {"availability_ratio": 0.930, "error_rate": 0.070, "audit_lag_seconds": 480.0},
    SyntheticFaultScenario.GOVERNANCE_BACKLOG.value: {"availability_ratio": 0.975, "error_rate": 0.025, "backlog_depth": 142.0},
}


class SyntheticTelemetryProvider(TelemetryProvider):
    """合成遥测 Provider（T3, T9）。

    所有输出信封 ``simulation_only=True``，且不可被篡改为真实生产数据（红线⑪）。
    """

    kind = ProviderKind.SYNTHETIC
    capabilities = [
        ProviderCapability.METRICS,
        ProviderCapability.HEALTH,
        ProviderCapability.LOGS,
        ProviderCapability.TRACES,
    ]

    def __init__(self, *, provider_id: str = "synthetic") -> None:
        self._provider_id = provider_id
        self._scenario = SyntheticFaultScenario.HEALTHY

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def is_configured(self) -> bool:
        # 合成源始终可用（作为模拟源），但所有数据 simuluation_only=True。
        return True

    def set_scenario(self, scenario: SyntheticFaultScenario) -> None:
        self._scenario = scenario

    @property
    def current_scenario(self) -> SyntheticFaultScenario:
        return self._scenario

    # ---- 端口实现 ----
    def query_health(
        self, *, organization_id: str, component: str
    ) -> List[TelemetryEnvelope]:
        spec = _SCENARIO_HEALTH.get(self._scenario.value, _SCENARIO_HEALTH["healthy"])
        comp = spec.get("component", component)
        return [
            self._envelope(
                telemetry_type=TelemetryType.HEALTH,
                organization_id=organization_id,
                component=comp,
                timestamp=_now(),
                payload={
                    "status": spec["status"],
                    "detail": spec["detail"],
                    "scenario": self._scenario.value,
                },
                simulation_only=True,
                integrity_status=IntegrityStatus.INTACT,
            )
        ]

    def query_metrics(
        self, *, organization_id: str, component: str, window: str = "5m"
    ) -> List[TelemetryEnvelope]:
        values = _SCENARIO_METRICS.get(self._scenario.value, _SCENARIO_METRICS["healthy"])
        return [
            self._envelope(
                telemetry_type=TelemetryType.METRIC,
                organization_id=organization_id,
                component=component,
                timestamp=_now(),
                payload={"window": window, "values": dict(values), "scenario": self._scenario.value},
                simulation_only=True,
                integrity_status=IntegrityStatus.INTACT,
            )
        ]

    def query_logs(
        self, *, organization_id: str, component: str, limit: int = 100
    ) -> List[TelemetryEnvelope]:
        spec = _SCENARIO_HEALTH.get(self._scenario.value, _SCENARIO_HEALTH["healthy"])
        comp = spec.get("component", component)
        level = "ERROR" if spec["status"] == "unhealthy" else "WARN" if spec["status"] == "degraded" else "INFO"
        return [
            self._envelope(
                telemetry_type=TelemetryType.LOG,
                organization_id=organization_id,
                component=comp,
                timestamp=_now(),
                payload={
                    "level": level,
                    "message": f"[{self._scenario.value}] {spec['detail']}",
                    "scenario": self._scenario.value,
                },
                simulation_only=True,
                integrity_status=IntegrityStatus.INTACT,
            )
        ]

    def query_traces(
        self, *, organization_id: str, component: str, limit: int = 50
    ) -> List[TelemetryEnvelope]:
        if self._scenario == SyntheticFaultScenario.HEALTHY:
            return []
        trace_id = f"trace-syn-{self._scenario.value}"
        return [
            self._envelope(
                telemetry_type=TelemetryType.TRACE,
                organization_id=organization_id,
                component=component,
                timestamp=_now(),
                payload={"trace_id": trace_id, "spans": [{"op": self._scenario.value, "error": True}]},
                simulation_only=True,
                trace_id=trace_id,
                integrity_status=IntegrityStatus.INTACT,
            )
        ]

    def provider_health(self) -> TelemetryProviderHealth:
        return TelemetryProviderHealth(
            provider_id=self._provider_id,
            kind=self.kind,
            status=ProviderStatus.CONFIGURED,
            checked_at=_now(),
            capabilities=self.capabilities,
            detail="synthetic simulation source; all envelopes simulation_only=True",
            simulation_only=True,
        )


class SyntheticFaultInjection:
    """逻辑层合成故障注入（T11）。

    红线⑥/⑭：只能注入 ``SyntheticTelemetryProvider``。向真实 Provider 注入即抛
    ``EnterpriseRedLineViolationError``（fail-closed）。
    """

    def inject(
        self,
        *,
        provider: TelemetryProvider,
        scenario: SyntheticFaultScenario,
        organization_id: str,
        component: str,
    ) -> List[TelemetryEnvelope]:
        if provider.kind != ProviderKind.SYNTHETIC:
            raise EnterpriseRedLineViolationError(
                "禁止向真实 Provider 注入故障（红线⑥/⑭）：仅允许 SyntheticTelemetryProvider"
            )
        if not isinstance(provider, SyntheticTelemetryProvider):
            raise EnterpriseRedLineViolationError(
                "故障注入目标必须是 SyntheticTelemetryProvider（红线⑥/⑭）"
            )
        provider.set_scenario(scenario)
        envelopes: List[TelemetryEnvelope] = []
        envelopes.extend(provider.query_health(organization_id=organization_id, component=component))
        envelopes.extend(
            provider.query_metrics(organization_id=organization_id, component=component)
        )
        envelopes.extend(provider.query_logs(organization_id=organization_id, component=component))
        envelopes.extend(provider.query_traces(organization_id=organization_id, component=component))
        return envelopes


__all__ = [
    "SyntheticTelemetryProvider",
    "SyntheticFaultInjection",
    "SyntheticFaultScenario",
]
