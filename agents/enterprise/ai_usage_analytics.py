"""Enterprise Analytics & Operation Intelligence Layer —— AI 使用分析（任务4，Phase 3.8.4）。

新增：``AIUsageAnalytics``，统计 AI 调用次数 / 任务类型 / 响应情况。
**禁止记录为人工行为**（采集时恒记 actor=AI；红线⑥：AI 动作如实标注为 AI，不伪造为人工）。

红线约束（fail-closed）：
- 所有统计按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- 构造断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
- **恒记 actor=AI**：``record_ai_usage`` 内部调用 ``AuditService.record_ai_action``，
  绝不调用 ``record_user_action`` 伪造为人工（红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


@dataclass
class AIUsageEvent:
    """单次 AI 使用事件（任务4）。

    恒记 actor=AI（recorded_by 仅作来源备注，不改变 actor 真实标注）；
    响应情况以 success / response_time 如实记录。
    """

    event_id: str
    org_id: str
    task_type: str                         # 任务类型（design_consult / vision / report ...）
    success: bool = True
    response_time: float = 0.0             # 响应耗时（秒）
    recorded_at: str = ""
    recorded_by: str = "ai"                # 恒为 ai（来源备注，非 actor 伪造）


@dataclass
class AIUsageAnalytics:
    """AI 使用分析（任务4）。

    统计 AI 调用次数 / 任务类型分布 / 响应情况（成功/失败/平均耗时）。
    **不**记录为人工行为（红线⑥）。
    """

    org_id: str
    analytics_id: str = ""
    total_calls: int = 0
    task_type_distribution: dict = field(default_factory=dict)  # {task_type: count}
    response_ok: int = 0
    response_fail: int = 0
    avg_response_time: float = 0.0
    computed_at: str = ""


class AIUsageAnalyticsService(_RedLineForbiddenMixin):
    """AI 使用分析服务（任务4）。

    统计 AI 调用与响应情况；**恒记 actor=AI**（红线⑥：不伪造为人工）。
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
        # 3.8.4 语义升级：禁止自动经营决策 / AI 代管理责任
        "auto_business_decision",
        "make_management_decision",
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AIUsageAnalyticsService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._events: dict[str, AIUsageEvent] = {}

    def record_ai_usage(
        self,
        *,
        event_id: str,
        task_type: str,
        success: bool = True,
        response_time: float = 0.0,
        recorded_at: str = "",
        recorded_by: str = "ai",
    ) -> AIUsageEvent:
        """记录一次 AI 使用事件（恒记 actor=AI，不伪造为人工；红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录 AI 使用（红线①/⑤）"
            )
        ev = AIUsageEvent(
            event_id=event_id,
            org_id=self._org_id,
            task_type=task_type,
            success=success,
            response_time=float(response_time),
            recorded_at=recorded_at,
            recorded_by="ai",   # 强制恒为 ai，来源备注不改 actor
        )
        self._events[event_id] = ev
        if self._audit is not None:
            # 红线⑥：如实标注 actor=AI，绝不调用 record_user_action 伪造为人工。
            self._audit.record_ai_action(
                record_id=f"ai-usage-{event_id}",
                actor_id="ai",
                action="record_ai_usage",
                target=event_id,
                detail=f"task_type={task_type};success={success};response_time={ev.response_time}",
                ts=recorded_at,
            )
        return ev

    def compute_analytics(self, *, analytics_id: str, computed_at: str = "") -> AIUsageAnalytics:
        """聚合 AI 使用事件，输出统计（不记录为人工；红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下聚合 AI 使用（红线①/⑤）"
            )
        events = [e for e in self._events.values() if e.org_id == self._org_id]
        total = len(events)
        dist: dict = {}
        ok = 0
        fail = 0
        rt_sum = 0.0
        for e in events:
            dist[e.task_type] = dist.get(e.task_type, 0) + 1
            if e.success:
                ok += 1
            else:
                fail += 1
            rt_sum += e.response_time
        analytics = AIUsageAnalytics(
            org_id=self._org_id,
            analytics_id=analytics_id,
            total_calls=total,
            task_type_distribution=dist,
            response_ok=ok,
            response_fail=fail,
            avg_response_time=(rt_sum / total) if total else 0.0,
            computed_at=computed_at,
        )
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"ai-usage-analytics-{analytics_id}",
                actor_id="ai",
                action="compute_ai_usage_analytics",
                target=analytics_id,
                detail=f"total={total};ok={ok};fail={fail}",
                ts=computed_at,
            )
        return analytics

    def list_events(self) -> list[AIUsageEvent]:
        """列出当前组织下 AI 使用事件（只读）。"""
        return [e for e in self._events.values() if e.org_id == self._org_id]


__all__ = ["AIUsageEvent", "AIUsageAnalytics", "AIUsageAnalyticsService"]
