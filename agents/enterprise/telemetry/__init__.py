"""Phase 3.9.4 生产遥测接入适配与合成运维验证包。

本包对外**只导出**：Provider 端口与各类适配器（Synthetic / Prometheus / OTel / Log）、
归一化器、健康聚合、Provider 注册表、告警路由端口（仅 Null / Synthetic）、合成故障注入、
领域模型、以及编排服务 ``ProductionTelemetryService``。

**绝不放行**的能力（结构性 fail-closed，由 forbidden 层拦截，且本 __init__ **不导出**任何
自动回滚 / 真实外发 / Runbook 执行入口）：

- 任何向真实服务注入故障的方法（``inject_production_fault`` 等）；
- 任何把合成遥测伪装成真实生产遥测 / 端口降级伪装的方法；
- 任何真实外发告警（``deliver_real_alert`` / ``send_real_pagerduty`` / ``send_real_slack`` /
  ``send_real_wechat`` / ``send_real_email`` / ``send_real_webhook`` 等）；
- 任何自动执行 Runbook / 自动 ACK-RESOLVE-CLOSE Incident / 经遥测自动部署回滚的方法。

这些名字仅作为 ``_RedLineForbiddenMixin`` 的拦截黑名单存在（见 ``forbidden.py`` 的
``TELEMETRY_FORBIDDEN_COUNT``），不在此导出、不在任何服务上以可达方法暴露。
"""

from __future__ import annotations

from agents.enterprise.telemetry.alert_routing import (
    AlertDeliveryStatus,
    AlertRoutingProvider,
    NullAlertRoutingProvider,
    SyntheticAlertRoutingProvider,
)
from agents.enterprise.telemetry.forbidden import (
    TELEMETRY_FORBIDDEN_COUNT,
    _TELEMETRY_FORBIDDEN,
)
from agents.enterprise.telemetry.health import TelemetryHealthAggregator
from agents.enterprise.telemetry.models import (
    IntegrityStatus,
    LogEvidence,
    OnCallScheduleReference,
    IncidentEscalationPolicy,
    ProviderCapability,
    ProviderKind,
    ProviderStatus,
    SyntheticFaultScenario,
    TelemetryEnvelope,
    TelemetryProviderHealth,
    TelemetryType,
    TraceReference,
)
from agents.enterprise.telemetry.log import SyntheticLogProvider
from agents.enterprise.telemetry.normalizer import TelemetryNormalizer
from agents.enterprise.telemetry.provider import TelemetryProvider
from agents.enterprise.telemetry.registry import TelemetryProviderRegistry
from agents.enterprise.telemetry.service import ProductionTelemetryService
from agents.enterprise.telemetry.synthetic import (
    SyntheticFaultInjection,
    SyntheticTelemetryProvider,
)

__all__ = [
    # Provider 端口与适配器
    "TelemetryProvider",
    "SyntheticTelemetryProvider",
    "SyntheticLogProvider",
    "SyntheticFaultInjection",
    # 归一化 / 健康 / 注册表
    "TelemetryNormalizer",
    "TelemetryHealthAggregator",
    "TelemetryProviderRegistry",
    # 告警路由端口（仅 Null / Synthetic，绝不真实外发）
    "AlertRoutingProvider",
    "NullAlertRoutingProvider",
    "SyntheticAlertRoutingProvider",
    "AlertDeliveryStatus",
    # 编排服务
    "ProductionTelemetryService",
    # 模型
    "TelemetryType",
    "ProviderKind",
    "ProviderStatus",
    "ProviderCapability",
    "IntegrityStatus",
    "TelemetryEnvelope",
    "TelemetryProviderHealth",
    "TraceReference",
    "LogEvidence",
    "SyntheticFaultScenario",
    "OnCallScheduleReference",
    "IncidentEscalationPolicy",
    # 红线禁名集（仅用于计数 / 文档，不导出任何可达能力）
    "TELEMETRY_FORBIDDEN_COUNT",
    "_TELEMETRY_FORBIDDEN",
]
