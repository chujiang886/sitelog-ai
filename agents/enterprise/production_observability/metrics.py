"""Phase 3.9.3 指标层（T3）。标准指标快照聚合。所有数值为事实描述，标记模拟来源。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.models import (
    MetricCategory,
    MetricSnapshot,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError, safety_invariants_ok


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MetricsService:
    """指标服务（T3）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir

    def snapshot(
        self,
        *,
        metric_id: str,
        category: MetricCategory,
        component: str,
        window: str,
        values: Dict[str, float],
        source: str,
        simulation_only: bool = False,
        checked_at: Optional[str] = None,
    ) -> MetricSnapshot:
        return MetricSnapshot(
            metric_id=metric_id,
            category=category,
            component=component,
            window=window,
            values=values,
            source=source,
            simulation_only=simulation_only,
            checked_at=checked_at or _now(),
        )

    def aggregate_availability(
        self, snapshots: List[MetricSnapshot]
    ) -> Dict[str, Any]:
        """聚合 availability 指标，输出 request/success/error 计数与可用率。"""
        req = sum(s.values.get("request_count", 0.0) for s in snapshots)
        succ = sum(s.values.get("success_count", 0.0) for s in snapshots)
        err = sum(s.values.get("error_count", 0.0) for s in snapshots)
        ratio = (succ / req) if req > 0 else 0.0
        return {
            "request_count": req,
            "success_count": succ,
            "error_count": err,
            "availability_ratio": ratio,
            "simulation_only": any(s.simulation_only for s in snapshots),
        }

    def aggregate_latency(self, snapshots: List[MetricSnapshot]) -> Dict[str, Any]:
        """聚合 latency 分位（p50/p95/p99）。"""

        def _pct(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            s = sorted(values)
            idx = min(len(s) - 1, int(p * (len(s) - 1)))
            return s[idx]

        p50 = _pct([s.values.get("p50", 0.0) for s in snapshots], 0.5)
        p95 = _pct([s.values.get("p95", 0.0) for s in snapshots], 0.95)
        p99 = _pct([s.values.get("p99", 0.0) for s in snapshots], 0.99)
        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "simulation_only": any(s.simulation_only for s in snapshots),
        }

    def by_component(self, snapshots: List[MetricSnapshot]) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for s in snapshots:
            out.setdefault(s.component, []).append(s.to_dict())
        return out
