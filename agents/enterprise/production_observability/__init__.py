"""Phase 3.9.3 企业生产可观测性、SRE 与事故响应准备层。

本包提供**纯可观测 / 被动监测 / 事故候选 / 响应草稿 / 复盘草稿**能力。它**不导出**任何
真实修复 / 真实回滚 / 真实部署 / 自动 ACK / 自动 RESOLVE / 自动 CLOSE / 自动指派指挥官 /
AI 代指挥 / 把模拟当真实的能力——这些禁名已在 ``forbidden.py`` 中被结构拦截，AI 无法越过。

仅供人工责任人基于只读事实做生产事故响应研判。
"""

from __future__ import annotations

from agents.enterprise.production_observability.alerts import AlertService
from agents.enterprise.production_observability.correlation import CorrelationEngine
from agents.enterprise.production_observability.forbidden import (
    PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT,
    _PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN,
    _PRODUCTION_OBSERVABILITY_FORBIDDEN,
)
from agents.enterprise.production_observability.health import ServiceHealthService
from agents.enterprise.production_observability.incidents import IncidentService
from agents.enterprise.production_observability.metrics import MetricsService
from agents.enterprise.production_observability.models import (
    AlertCandidate,
    AlertStatus,
    ErrorBudget,
    IncidentCandidate,
    IncidentCommanderAssignment,
    IncidentFollowUpCandidate,
    IncidentPostmortemDraft,
    IncidentRecoveryValidation,
    IncidentResponseDraft,
    IncidentRunbookReference,
    IncidentSeverity,
    IncidentStatus,
    IncidentTimelineEvent,
    MetricCategory,
    MetricSnapshot,
    ObservableComponent,
    ObservabilityCorrelation,
    ProductionIncident,
    RootCauseStatus,
    SecurityAlertCandidate,
    ServiceHealth,
    ServiceHealthStatus,
    SLIDefinition,
    SLODefinition,
    SLOKind,
    SLOStatus,
)
from agents.enterprise.production_observability.slo import SLOService
from agents.enterprise.production_observability.service import (
    ProductionObservabilityError,
    ProductionObservabilityService,
)

__all__ = [
    # 服务
    "ProductionObservabilityService",
    "ProductionObservabilityError",
    "ServiceHealthService",
    "MetricsService",
    "SLOService",
    "AlertService",
    "IncidentService",
    "CorrelationEngine",
    # 模型
    "ServiceHealthStatus",
    "ObservableComponent",
    "ServiceHealth",
    "MetricCategory",
    "MetricSnapshot",
    "SLOKind",
    "SLIDefinition",
    "SLOStatus",
    "SLODefinition",
    "ErrorBudget",
    "AlertStatus",
    "AlertCandidate",
    "ObservabilityCorrelation",
    "IncidentStatus",
    "IncidentSeverity",
    "IncidentCandidate",
    "IncidentTimelineEvent",
    "ProductionIncident",
    "IncidentCommanderAssignment",
    "IncidentRunbookReference",
    "IncidentResponseDraft",
    "IncidentRecoveryValidation",
    "RootCauseStatus",
    "IncidentPostmortemDraft",
    "IncidentFollowUpCandidate",
    "SecurityAlertCandidate",
    # 禁名集
    "PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT",
    "_PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN",
    "_PRODUCTION_OBSERVABILITY_FORBIDDEN",
]
