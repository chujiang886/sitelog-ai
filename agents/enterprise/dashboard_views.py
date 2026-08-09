"""Enterprise Intelligence Dashboard Layer —— 企业视图（任务3，Phase 3.8.5）。

新增：``ProjectDashboard`` / ``WorkflowDashboard`` / ``AIDashboard`` / ``RiskDashboard``。

设计要点：
- 四个视图**只读组合** Phase 3.8.4 既有 analytics 子服务的计算结果（``ProjectAnalytics`` /
  ``WorkflowAnalytics`` / ``AIUsageAnalytics`` / ``list[RiskCandidate]``），将其拆解为事实型
  ``DashboardWidget``（metric / chart / table / risk）。
- **只展示事实**：不评价、不决策、不代管理做判断（红线③/⑥）。例如 ``WorkflowAnalytics.insight``
  仅作为描述性 widget.note，不进入 facts；``RiskCandidate`` 仅列出并要求人工确认的事实。
- 视图构建本身是纯只读装配，**不**写任何数据、不持有任何批准/报价/审批/记录为人工方法
  （红线②/③/④/⑥）。
- 各视图打上对应 ``source`` 标记（project_analytics / workflow_analytics / ai_usage_analytics /
  operation_risk），供 ``AnalyticsVisibilityPolicy`` 按角色过滤。
"""

from __future__ import annotations

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.dashboard import Dashboard, DashboardWidget, WidgetType
from agents.enterprise.operation_risk import RiskCandidate, RiskSeverity
from agents.enterprise.project_analytics import ProjectAnalytics
from agents.enterprise.workflow_analytics import WorkflowAnalytics


class ProjectDashboard:
    """项目驾驶舱（任务3）：只读组合 ``ProjectAnalytics`` 事实。"""

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def build(
        self,
        *,
        dashboard_id: str,
        owner_id: str,
        analytics: ProjectAnalytics,
        created_at: str = "",
    ) -> Dashboard:
        widgets = [
            DashboardWidget(
                widget_id="prj-total",
                widget_type=WidgetType.METRIC,
                title="项目总数",
                facts={"total_projects": analytics.total_projects},
                source="project_analytics",
            ),
            DashboardWidget(
                widget_id="prj-completion",
                widget_type=WidgetType.METRIC,
                title="完成与完成率",
                facts={
                    "completed_count": analytics.completed_count,
                    "completion_rate": analytics.completion_rate,
                },
                source="project_analytics",
            ),
            DashboardWidget(
                widget_id="prj-cycle",
                widget_type=WidgetType.METRIC,
                title="平均周期（天）",
                facts={"avg_cycle_days": analytics.avg_cycle_days},
                source="project_analytics",
            ),
            DashboardWidget(
                widget_id="prj-status",
                widget_type=WidgetType.TABLE,
                title="状态分布",
                facts={"status_distribution": analytics.status_distribution},
                source="project_analytics",
            ),
        ]
        return Dashboard(
            dashboard_id=dashboard_id,
            org_id=self._org_id,
            owner_id=owner_id,
            widgets=widgets,
            visibility="org",
            created_at=created_at,
        )


class WorkflowDashboard:
    """流程效率驾驶舱（任务3）：只读组合 ``WorkflowAnalytics`` 事实。"""

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def build(
        self,
        *,
        dashboard_id: str,
        owner_id: str,
        analytics: WorkflowAnalytics,
        created_at: str = "",
    ) -> Dashboard:
        widgets = [
            DashboardWidget(
                widget_id="wf-stage-duration",
                widget_type=WidgetType.CHART,
                title="各阶段累计耗时",
                facts={"stage_duration": analytics.stage_duration},
                source="workflow_analytics",
            ),
            DashboardWidget(
                widget_id="wf-sla-status",
                widget_type=WidgetType.TABLE,
                title="SLA 状态分布",
                facts={"sla_status": analytics.sla_status},
                source="workflow_analytics",
            ),
            DashboardWidget(
                widget_id="wf-bottleneck",
                widget_type=WidgetType.METRIC,
                title="瓶颈阶段（耗时最大）",
                facts={"bottleneck": analytics.bottleneck},
                source="workflow_analytics",
                note=analytics.insight,   # 描述性洞察，非决策，不入 facts
            ),
        ]
        return Dashboard(
            dashboard_id=dashboard_id,
            org_id=self._org_id,
            owner_id=owner_id,
            widgets=widgets,
            visibility="org",
            created_at=created_at,
        )


class AIDashboard:
    """AI 使用驾驶舱（任务3）：只读组合 ``AIUsageAnalytics`` 事实。"""

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def build(
        self,
        *,
        dashboard_id: str,
        owner_id: str,
        analytics: AIUsageAnalytics,
        created_at: str = "",
    ) -> Dashboard:
        widgets = [
            DashboardWidget(
                widget_id="ai-total-calls",
                widget_type=WidgetType.METRIC,
                title="AI 调用总数",
                facts={"total_calls": analytics.total_calls},
                source="ai_usage_analytics",
            ),
            DashboardWidget(
                widget_id="ai-task-dist",
                widget_type=WidgetType.TABLE,
                title="任务类型分布",
                facts={"task_type_distribution": analytics.task_type_distribution},
                source="ai_usage_analytics",
            ),
            DashboardWidget(
                widget_id="ai-response",
                widget_type=WidgetType.METRIC,
                title="响应情况",
                facts={
                    "response_ok": analytics.response_ok,
                    "response_fail": analytics.response_fail,
                    "avg_response_time": analytics.avg_response_time,
                },
                source="ai_usage_analytics",
            ),
        ]
        return Dashboard(
            dashboard_id=dashboard_id,
            org_id=self._org_id,
            owner_id=owner_id,
            widgets=widgets,
            visibility="org",
            created_at=created_at,
        )


class RiskDashboard:
    """风险驾驶舱（任务3）：只读组合 ``RiskCandidate`` 事实列表（均要求人工确认）。"""

    def __init__(self, org_id: str) -> None:
        self._org_id = org_id

    def build(
        self,
        *,
        dashboard_id: str,
        owner_id: str,
        candidates: "list[RiskCandidate]",
        created_at: str = "",
    ) -> Dashboard:
        risk_facts = [
            {
                "risk_id": c.risk_id,
                "risk_type": c.risk_type,
                "severity": c.severity.value if isinstance(c.severity, RiskSeverity) else str(c.severity),
                "description": c.description,
                "evidence": c.evidence,
                "requires_human_confirmation": c.requires_human_confirmation,
            }
            for c in candidates
        ]
        widgets = [
            DashboardWidget(
                widget_id="risk-list",
                widget_type=WidgetType.RISK,
                title="风险候选清单（均要求人工确认）",
                facts={"risks": risk_facts, "total": len(risk_facts)},
                source="operation_risk",
                note="以上为 AI 检测输出的风险事实，须由人工确认与处置，AI 不作判定",
            ),
        ]
        return Dashboard(
            dashboard_id=dashboard_id,
            org_id=self._org_id,
            owner_id=owner_id,
            widgets=widgets,
            visibility="org",
            created_at=created_at,
        )


__all__ = [
    "ProjectDashboard",
    "WorkflowDashboard",
    "AIDashboard",
    "RiskDashboard",
]
