"""Enterprise Analytics & Operation Intelligence Layer —— 项目分析（任务2，Phase 3.8.4）。

新增：``ProjectAnalytics``，分析项目数量 / 完成率 / 周期 / 状态分布。
**禁止评价工程质量**（不提供任何质量评分/质量评估入口；红线③/⑥：AI 不代管理做判断）。

红线约束（fail-closed）：
- 只读分析 ``ProjectService``；跨域访问抛 ``EnterpriseIsolationError``。
- 构造断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
- **无工程质量评价入口**：不提供 evaluate_quality / score_project 等（红线③/⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.project import ProjectService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class ProjectStatus(str, Enum):
    """项目状态枚举（仅用于统计分组，不做质量评价）。"""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class ProjectAnalytics:
    """项目分析（任务2）。

    仅统计事实：项目数量 / 完成率 / 平均周期 / 状态分布。
    **不**包含任何工程质量评价字段（红线③/⑥）。
    """

    org_id: str
    total_projects: int = 0
    completed_count: int = 0
    completion_rate: float = 0.0          # 完成率（completed / total），0~1
    avg_cycle_days: float = 0.0           # 平均周期（天），无起止数据时为 0
    status_distribution: dict = field(default_factory=dict)  # {status: count}
    analytics_id: str = ""
    computed_at: str = ""
    notes: str = ""                       # 仅事实描述，不含评价/决策


# 完成态判定：archived 视为已完成（业务事实约定，非质量评价）。
_COMPLETED_STATUSES = ("archived",)


class ProjectAnalyticsService(_RedLineForbiddenMixin):
    """项目分析服务（任务2）。

    只读分析 ProjectService，输出事实统计；**不**评价工程质量。
    跨域访问抛 ``EnterpriseIsolationError``；构造断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.4 语义升级：禁止自动经营决策 / AI 代管理责任 / 工程质量评价
        "evaluate_quality",
        "score_project",
        "auto_business_decision",
        "make_management_decision",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        project_service: "ProjectService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "ProjectAnalyticsService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._projects = project_service or ProjectService(org_id=org_id)

    def compute_project_analytics(
        self,
        *,
        analytics_id: str,
        computed_at: str = "",
        cycle_days_by_project: "dict[str, float] | None" = None,
    ) -> ProjectAnalytics:
        """只读分析当前组织项目，输出事实统计（不评价工程质量；红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分析项目（红线①/⑤）"
            )
        projects = self._projects.list_projects()
        total = len(projects)
        status_dist: dict = {}
        completed = 0
        for p in projects:
            st = p.status or "draft"
            status_dist[st] = status_dist.get(st, 0) + 1
            if st in _COMPLETED_STATUSES:
                completed += 1
        completion_rate = (completed / total) if total else 0.0
        cycle = dict(cycle_days_by_project or {})
        cycle_vals = [v for pid, v in cycle.items() if any(p.project_id == pid for p in projects)]
        avg_cycle = (sum(cycle_vals) / len(cycle_vals)) if cycle_vals else 0.0
        analytics = ProjectAnalytics(
            org_id=self._org_id,
            total_projects=total,
            completed_count=completed,
            completion_rate=completion_rate,
            avg_cycle_days=avg_cycle,
            status_distribution=status_dist,
            analytics_id=analytics_id,
            computed_at=computed_at,
            notes="仅统计事实，不含工程质量评价",
        )
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"project-analytics-{analytics_id}",
                actor_id="ai",
                action="compute_project_analytics",
                target=analytics_id,
                detail=f"total={total};completed={completed};completion_rate={completion_rate}",
                ts=computed_at,
            )
        return analytics


__all__ = ["ProjectStatus", "ProjectAnalytics", "ProjectAnalyticsService"]
