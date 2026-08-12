"""Phase 3.9.4 遥测归一化层（T7, T13）。

``TelemetryNormalizer`` 把不同 Provider 的 ``TelemetryEnvelope`` 统一归一为
``ProductionObservabilityService`` 核心业务层已经消费的 **标准业务对象**：

- ``ServiceHealth`` / ``ServiceHealthStatus``（健康）
- ``MetricSnapshot`` / ``MetricCategory``（指标）
- ``TraceReference``（链路追踪）
- ``LogEvidence``（日志）

设计纪律（红线⑪/⑭）：

- Provider 的实现差异（Prometheus / OTel / Loki 各自响应结构）**绝不**向上泄漏到
  可观测性核心业务层；高层只见到上面四类标准对象。
- Synthetic 信封的 ``simulation_only`` 标记在归一后仍被保留（标准对象同样带
  ``simulation_only``），**绝不**被抹除或篡改为真实生产数据。
- 任何归一失败都 fail-closed：返回降级快照（``status=UNKNOWN`` 或
  ``simulation_only`` 原样保留），不抛异常伪装成功。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from agents.enterprise.production_observability.models import (
    MetricCategory,
    MetricSnapshot,
    ServiceHealth,
    ServiceHealthStatus,
)
from agents.enterprise.telemetry.models import (
    LogEvidence,
    TelemetryEnvelope,
    TelemetryType,
    TraceReference,
)


def _metric_category_for(scenario: str) -> MetricCategory:
    """把合成场景映射到可观测层的指标大类（仅描述性，无真实业务阈值）。"""
    if scenario == "release_regression":
        return MetricCategory.RELEASE
    if scenario in ("identity_authentication_failure", "permission_denial_spike"):
        return MetricCategory.IDENTITY
    if scenario in ("llm_timeout", "asr_unavailable", "tts_unavailable"):
        return MetricCategory.AI_RUNTIME
    if scenario in ("governance_backlog",):
        return MetricCategory.GOVERNANCE
    return MetricCategory.AVAILABILITY


def _status_from_str(value: str) -> ServiceHealthStatus:
    try:
        return ServiceHealthStatus(value)
    except ValueError:
        # fail-closed：未知状态一律视为 UNKNOWN，绝不回退 HEALTHY（红线⑪）。
        return ServiceHealthStatus.UNKNOWN


class TelemetryNormalizer:
    """遥测归一化器（T7, T13）。

    把 ``TelemetryEnvelope`` 列表按 ``telemetry_type`` 路由到对应标准对象工厂。
    """

    def normalize(self, envelopes: List[TelemetryEnvelope]) -> Dict[str, List[Any]]:
        """批量归一。返回 ``{health: [...], metrics: [...], traces: [...], logs: [...]}``。"""
        out: Dict[str, List[Any]] = {
            "health": [],
            "metrics": [],
            "traces": [],
            "logs": [],
        }
        for env in envelopes or []:
            t = env.telemetry_type
            if t == TelemetryType.HEALTH:
                out["health"].append(self.normalize_health(env))
            elif t == TelemetryType.METRIC:
                out["metrics"].append(self.normalize_metric(env))
            elif t == TelemetryType.TRACE:
                out["traces"].append(self.normalize_trace(env))
            elif t == TelemetryType.LOG:
                out["logs"].append(self.normalize_log(env))
            else:
                # EVIDENCE 等不参与归一，丢弃（fail-closed：不影响主链路）。
                continue
        return out

    def normalize_health(self, env: TelemetryEnvelope) -> ServiceHealth:
        payload = env.payload or {}
        status = _status_from_str(str(payload.get("status", "unknown")))
        return ServiceHealth(
            component=env.component,
            status=status,
            checked_at=env.timestamp,
            source=env.provider,
            evidence=str(payload.get("detail", "")),
            trace_reference=env.trace_id or "",
        )

    def normalize_metric(self, env: TelemetryEnvelope) -> MetricSnapshot:
        payload = env.payload or {}
        values: Dict[str, float] = {}
        raw_values = payload.get("values")
        if isinstance(raw_values, dict):
            for k, v in raw_values.items():
                try:
                    values[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
        scenario = str(payload.get("scenario", ""))
        window = str(payload.get("window", "5m"))
        category = _metric_category_for(scenario)
        return MetricSnapshot(
            metric_id=f"m-{env.component}-{scenario or 'adhoc'}",
            category=category,
            component=env.component,
            window=window,
            values=values,
            source=env.provider,
            simulation_only=bool(env.simulation_only),
            checked_at=env.timestamp,
        )

    def normalize_trace(self, env: TelemetryEnvelope) -> TraceReference:
        payload = env.payload or {}
        spans = payload.get("spans") or []
        service = str(payload.get("service", env.component))
        trace_id = str(payload.get("trace_id", env.trace_id))
        return TraceReference(
            trace_id=trace_id,
            service=service,
            spans=list(spans),
            governance_trace_id="",
            release_id=env.release_id or "",
            incident_id="",
        )

    def normalize_log(self, env: TelemetryEnvelope) -> LogEvidence:
        payload = env.payload or {}
        source = str(payload.get("source", env.provider))
        return LogEvidence(
            log_id=f"log-{uuid.uuid4().hex[:12]}",
            source=source,
            level=str(payload.get("level", "INFO")),
            message=str(payload.get("message", "")),
            timestamp=env.timestamp,
            component=env.component,
            trace_id=env.trace_id or "",
        )


__all__ = ["TelemetryNormalizer", "_status_from_str", "_metric_category_for"]
