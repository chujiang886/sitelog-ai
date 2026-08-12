"""Phase 3.9.3 服务健康服务（T2）。只读采集 + 聚合，UNKNOWN 永不当 HEALTHY。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.models import (
    ObservableComponent,
    ServiceHealth,
    ServiceHealthStatus,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError, safety_invariants_ok


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ServiceHealthService:
    """统一健康状态服务（T2）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir

    def snapshot(
        self,
        *,
        component: str,
        status: ServiceHealthStatus,
        source: str,
        evidence: str = "",
        latency_ms: Optional[float] = None,
        error: str = "",
        trace_reference: str = "",
        checked_at: Optional[str] = None,
    ) -> ServiceHealth:
        """构造单次组件健康快照（只描述事实）。"""
        return ServiceHealth(
            component=component,
            status=status,
            checked_at=checked_at or _now(),
            source=source,
            evidence=evidence,
            latency_ms=latency_ms,
            error=error,
            trace_reference=trace_reference,
        )

    def overall_status(self, snapshots: List[ServiceHealth]) -> ServiceHealthStatus:
        """聚合总览健康：任一 UNHEALTHY → UNHEALTHY；否则任一 DEGRADED → DEGRADED；
        否则任一 UNKNOWN → UNKNOWN（**绝不**回退到 HEALTHY，红线⑨/⑪）；全 HEALTHY →
        HEALTHY。"""
        if not snapshots:
            return ServiceHealthStatus.UNKNOWN
        statuses = {s.status for s in snapshots}
        if ServiceHealthStatus.UNHEALTHY in statuses:
            return ServiceHealthStatus.UNHEALTHY
        if ServiceHealthStatus.DEGRADED in statuses:
            return ServiceHealthStatus.DEGRADED
        if ServiceHealthStatus.UNKNOWN in statuses:
            # 关键纪律：UNKNOWN 不得自动当 HEALTHY。
            return ServiceHealthStatus.UNKNOWN
        return ServiceHealthStatus.HEALTHY

    def is_operational(self, status: ServiceHealthStatus) -> bool:
        return ServiceHealthStatus.is_operational(status)

    def expected_components(self) -> List[str]:
        return [c.value for c in ObservableComponent]

    def to_summary(self, snapshots: List[ServiceHealth]) -> Dict[str, Any]:
        return {
            "overall": self.overall_status(snapshots).value,
            "components": [s.to_dict() for s in snapshots],
            "expected_components": self.expected_components(),
        }
