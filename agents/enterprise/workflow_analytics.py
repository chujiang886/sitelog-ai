"""Enterprise Analytics & Operation Intelligence Layer —— 流程效率分析（任务3，Phase 3.8.4）。

新增：``WorkflowAnalytics``，分析 stage_duration / sla_status / bottleneck，输出洞察。
**禁止自动修改流程**（不提供任何 modify_workflow / update_workflow / auto_fix 入口；红线③/⑥）。

红线约束（fail-closed）：
- 只读分析 ``WorkflowMetricsService`` + ``WorkflowSLAService``；跨域访问抛隔离错误。
- 构造断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
- **无流程修改入口**：不提供 modify_workflow / update_workflow / auto_fix（红线③/⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.workflow_metrics import WorkflowMetricsService
from agents.enterprise.workflow_sla import WorkflowSLAService, WorkflowSLAStatus


@dataclass
class WorkflowAnalytics:
    """流程效率分析（任务3）。

    仅输出事实洞察：stage_duration（各阶段耗时）/ sla_status（SLA 状态分布）/
    bottleneck（瓶颈阶段，由耗时最大者推导）/ insight（纯描述性洞察）。
    **不**含任何流程修改动作（红线③/⑥）。
    """

    org_id: str
    analytics_id: str = ""
    stage_duration: dict = field(default_factory=dict)   # {stage_name: 累计耗时}
    sla_status: dict = field(default_factory=dict)        # {status: count}
    bottleneck: str = ""                                  # 耗时最大阶段（事实推导）
    insight: str = ""                                     # 纯描述性洞察，非决策
    computed_at: str = ""


class WorkflowAnalyticsService(_RedLineForbiddenMixin):
    """流程效率分析服务（任务3）。

    只读分析 workflow_metrics + workflow_slas，输出洞察；**不**自动修改流程。
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
        # 3.8.4 语义升级：禁止自动经营决策 / AI 代管理责任 / 自动修改流程
        "modify_workflow",
        "update_workflow",
        "auto_fix",
        "auto_business_decision",
        "make_management_decision",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        metrics_service: "WorkflowMetricsService | None" = None,
        sla_service: "WorkflowSLAService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowAnalyticsService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._metrics = metrics_service or WorkflowMetricsService(org_id=org_id)
        self._slas = sla_service or WorkflowSLAService(org_id=org_id)

    def compute_workflow_analytics(
        self,
        *,
        analytics_id: str,
        computed_at: str = "",
    ) -> WorkflowAnalytics:
        """只读分析流程统计 + SLA，输出事实洞察（不修改流程；红线③/⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分析流程效率（红线①/⑤）"
            )
        metrics = self._metrics.list_metrics()
        # 累加各阶段耗时
        stage_duration: dict = {}
        for m in metrics:
            for stage, dur in (m.stage_time or {}).items():
                stage_duration[stage] = stage_duration.get(stage, 0.0) + float(dur)
        # 瓶颈 = 累计耗时最大的阶段（事实推导，非决策）
        bottleneck = ""
        if stage_duration:
            bottleneck = max(stage_duration, key=lambda k: stage_duration[k])
        # SLA 状态分布
        slas = self._slas.list_slas()
        sla_status: dict = {}
        for s in slas:
            key = s.status.value if isinstance(s.status, WorkflowSLAStatus) else str(s.status)
            sla_status[key] = sla_status.get(key, 0) + 1
        # 洞察：纯描述性，不含任何处置/决策指令
        overdue = sla_status.get(WorkflowSLAStatus.OVERDUE.value, 0)
        warning = sla_status.get(WorkflowSLAStatus.WARNING.value, 0)
        on_track = sla_status.get(WorkflowSLAStatus.ON_TRACK.value, 0)
        insight_parts = []
        if bottleneck:
            insight_parts.append(
                f"耗时最长的阶段为「{bottleneck}」（累计 {stage_duration[bottleneck]:.2f}）"
            )
        if overdue:
            insight_parts.append(f"存在 {overdue} 条 SLA 已逾期（OVERDUE），建议人工排查")
        elif warning:
            insight_parts.append(f"存在 {warning} 条 SLA 处于预警（WARNING），建议关注")
        else:
            insight_parts.append(f"当前 {on_track} 条 SLA 均在期内（ON_TRACK）")
        insight = "；".join(insight_parts) if insight_parts else "暂无足够数据生成洞察"
        analytics = WorkflowAnalytics(
            org_id=self._org_id,
            analytics_id=analytics_id,
            stage_duration=stage_duration,
            sla_status=sla_status,
            bottleneck=bottleneck,
            insight=insight,
            computed_at=computed_at,
        )
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"workflow-analytics-{analytics_id}",
                actor_id="ai",
                action="compute_workflow_analytics",
                target=analytics_id,
                detail=f"stages={len(stage_duration)};bottleneck={bottleneck};overdue={overdue}",
                ts=computed_at,
            )
        return analytics


__all__ = ["WorkflowAnalytics", "WorkflowAnalyticsService"]
