"""Phase 3.9.3 SLI/SLO 与错误预算（T4, T5）。阈值无真实业务目标时 pending_verification。

红线约束：
- 真实业务阈值必须由人工设定，否则 ``threshold_verified=False``（红线⑪）。
- 错误预算**禁止** AI 自动停止发布 / 自动回滚（红线⑤/③）；只生成状态 / 证据 /
  警告 / human_review_required。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.models import (
    ErrorBudget,
    SLODefinition,
    SLOKind,
    SLIDefinition,
    SLOStatus,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError, safety_invariants_ok


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SLOService:
    """SLI/SLO 与错误预算服务（T4, T5）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir

    def define_sli(
        self,
        *,
        sli_id: str,
        name: str,
        component: str,
        expression: str,
        simulation_only: bool = True,
    ) -> SLIDefinition:
        return SLIDefinition(
            sli_id=sli_id,
            name=name,
            component=component,
            expression=expression,
            simulation_only=simulation_only,
        )

    def define_slo(
        self,
        *,
        slo_id: str,
        name: str,
        component: str,
        kind: SLOKind,
        target: float,
        window: str = "30d",
        threshold_verified: bool = False,
        observed: Optional[float] = None,
    ) -> SLODefinition:
        # 阈值未经验证 → 状态恒 PENDING_VERIFICATION（红线⑪）。
        if not threshold_verified:
            status = SLOStatus.PENDING_VERIFICATION
        elif observed is None:
            status = SLOStatus.PENDING_VERIFICATION
        else:
            status = SLOStatus.MET if observed >= target else SLOStatus.BREACHED
        return SLODefinition(
            slo_id=slo_id,
            name=name,
            component=component,
            kind=kind,
            target=target,
            window=window,
            threshold_verified=threshold_verified,
            status=status,
        )

    def compute_error_budget(
        self,
        *,
        slo_id: str,
        budget_total: float,
        consumed: float,
        window: str = "30d",
        human_review_required: bool = False,
    ) -> ErrorBudget:
        # 红线⑤/③：本方法只计算，不触发任何停发布 / 回滚动作。
        return ErrorBudget(
            slo_id=slo_id,
            budget_total=budget_total,
            consumed=consumed,
            window=window,
            human_review_required=human_review_required,
        )

    def summarize(self, slos: List[SLODefinition]) -> Dict[str, Any]:
        return {
            "total": len(slos),
            "met": sum(1 for s in slos if s.status == SLOStatus.MET),
            "breached": sum(1 for s in slos if s.status == SLOStatus.BREACHED),
            "pending_verification": sum(
                1 for s in slos if s.status == SLOStatus.PENDING_VERIFICATION
            ),
            "items": [s.to_dict() for s in slos],
        }
