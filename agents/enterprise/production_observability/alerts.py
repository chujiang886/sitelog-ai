"""Phase 3.9.3 告警候选服务（T6, T7）。AI 可检测 / 聚合 / 生成；ACK/RESOLVE 必须人工。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.correlation import CorrelationEngine
from agents.enterprise.production_observability.models import (
    AlertCandidate,
    AlertStatus,
    ObservabilityCorrelation,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AlertService(_RedLineForbiddenMixin):
    """告警候选服务（T6, T7）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir
        self._correlator = CorrelationEngine(root_dir=root_dir)
        self._alerts: Dict[str, AlertCandidate] = {}

    # ------------------------------------------------------------------ #
    # 创建（AI 检测 / 聚合 / 生成候选）
    # ------------------------------------------------------------------ #
    def create_alert(
        self,
        *,
        alert_id: str,
        component: str,
        title: str,
        severity: str,
        detection_source: str,
        fingerprint: str,
        related_incident_id: Optional[str] = None,
        trace_ids: Optional[List[str]] = None,
        workflow_ids: Optional[List[str]] = None,
        release_id: Optional[str] = None,
        evidence: str = "",
        simulation_only: bool = False,
        detected_at: Optional[str] = None,
    ) -> AlertCandidate:
        al = AlertCandidate(
            alert_id=alert_id,
            component=component,
            title=title,
            severity=severity,
            status=AlertStatus.DETECTED,
            detection_source=detection_source,
            fingerprint=fingerprint,
            related_incident_id=related_incident_id,
            trace_ids=trace_ids,
            workflow_ids=workflow_ids,
            release_id=release_id,
            evidence=evidence,
            simulation_only=simulation_only,
            detected_at=detected_at or _now(),
        )
        self._alerts[alert_id] = al
        return al

    # ------------------------------------------------------------------ #
    # 去重 / 关联
    # ------------------------------------------------------------------ #
    def correlate(
        self, *, organization_id: str, alerts: Optional[List[AlertCandidate]] = None,
        time_window: str = "10m",
    ) -> List[ObservabilityCorrelation]:
        return self._correlator.correlate(
            organization_id=organization_id,
            alerts=alerts if alerts is not None else list(self._alerts.values()),
            time_window=time_window,
        )

    # ------------------------------------------------------------------ #
    # 人工动作（USER 强制；AI 主体 403 / 结构拦截）
    # ------------------------------------------------------------------ #
    def acknowledge(self, *, alert_id: str, actor_id: str, actor_kind: str) -> AlertCandidate:
        """人工 ACK。AI 不得调用（红线⑨）。"""
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "告警 ACK 必须由真实 USER 执行（红线⑨/⑩）"
            )
        al = self._alerts[alert_id]
        al.status = AlertStatus.ACKNOWLEDGED_BY_HUMAN
        return al

    def resolve(self, *, alert_id: str, actor_id: str, actor_kind: str) -> AlertCandidate:
        """人工 RESOLVE。AI 不得调用（红线⑨）。"""
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "告警 RESOLVE 必须由真实 USER 执行（红线⑨/⑩）"
            )
        al = self._alerts[alert_id]
        al.status = AlertStatus.RESOLVED_BY_HUMAN
        return al

    def get(self, alert_id: str) -> Optional[AlertCandidate]:
        return self._alerts.get(alert_id)

    def all(self) -> List[AlertCandidate]:
        return list(self._alerts.values())
