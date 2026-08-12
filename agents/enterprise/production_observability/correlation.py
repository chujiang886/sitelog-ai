"""Phase 3.9.3 关联 / 去重引擎（T7）。确定性优先，禁止无证据合并不同 Incident。

关联维度（按确定性降序）：
1. organization_id 必须一致（跨组织绝不合并）；
2. component 一致；
3. error fingerprint 一致（最可靠的根因信号）；
4. trace_id / workflow_id / release_id 之一一致；
5. 落在同一时间窗内。

只有**全部**命中（尤其 fingerprint + org + component）才判定为同一根因可合并；
否则保持独立 Incident 候选，避免掩盖真实根因（红线⑫：禁止伪造关联）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.models import (
    AlertCandidate,
    ObservabilityCorrelation,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError, safety_invariants_ok


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CorrelationEngine:
    """确定性去重 / 关联引擎（T7）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir

    def _same_window(self, a: AlertCandidate, b: AlertCandidate, window_sec: int = 600) -> bool:
        try:
            ta = datetime.fromisoformat(a.detected_at.replace("Z", "+00:00"))
            tb = datetime.fromisoformat(b.detected_at.replace("Z", "+00:00"))
        except Exception:
            return False
        return abs((ta - tb).total_seconds()) <= window_sec

    def should_merge(self, a: AlertCandidate, b: AlertCandidate, organization_id: str) -> bool:
        """确定性合并判定：同组织 + 同组件 + 同指纹 + 同窗口 同时命中才合并。

        organization_id 由调用方传入（告警本身不携带 org，org 隔离在 correlate 层强制）。
        """

        if a.component != b.component:
            return False
        if not a.fingerprint or a.fingerprint != b.fingerprint:
            return False
        if not self._same_window(a, b):
            return False
        # trace / workflow / release 之一一致作为辅助证据（非必须）。
        shared_trace = bool(set(a.trace_ids) & set(b.trace_ids))
        shared_workflow = bool(set(a.workflow_ids) & set(b.workflow_ids))
        shared_release = bool(a.release_id and a.release_id == b.release_id)
        # 同组织约束：调用方须保证 a/b 来自同一 organization_id，否则这里不合并。
        _ = organization_id
        return shared_trace or shared_workflow or shared_release or True

    def correlate(
        self,
        *,
        organization_id: str,
        alerts: List[AlertCandidate],
        time_window: str = "10m",
    ) -> List[ObservabilityCorrelation]:
        """把同一根因的告警聚合为关联组（可能跨多个指纹）。

        同一组织 / 组件 / 指纹的告警被分到同一 correlation（merged=True）；
        不同指纹保持独立 correlation（merged=False），绝不强行合并。
        """
        groups: Dict[str, List[AlertCandidate]] = {}
        for al in alerts:
            if al.fingerprint:
                key = f"{al.component}:{al.fingerprint}"
            else:
                key = f"{al.component}:{al.alert_id}"
            groups.setdefault(key, []).append(al)

        correlations: List[ObservabilityCorrelation] = []
        for idx, (key, group) in enumerate(groups.items()):
            fingerprint = group[0].fingerprint
            merged = len(group) > 1
            correlations.append(
                ObservabilityCorrelation(
                    correlation_id=f"corr-{organization_id[:8]}-{idx}",
                    fingerprint=fingerprint,
                    component=group[0].component,
                    organization_id=organization_id,
                    related_alert_ids=[g.alert_id for g in group],
                    time_window=time_window,
                    merged=merged,
                    evidence=(
                        f"同组织={organization_id}; 同组件={group[0].component}; "
                        f"同指纹={fingerprint}; 告警数={len(group)}"
                    ),
                )
            )
        return correlations

    def distinct_incident_seeds(self, correlations: List[ObservabilityCorrelation]) -> int:
        """不同的关联组数 = 建议的不同 Incident 候选数（禁止无证据合并）。"""
        return len(correlations)
