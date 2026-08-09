"""Enterprise Intelligence Dashboard Layer —— 测试3：四类企业视图（Phase 3.8.5）。

覆盖（任务3 落地校验）：
- ProjectDashboard / WorkflowDashboard / AIDashboard / RiskDashboard 只读组合 3.8.4 事实。
- 各视图组件均为事实型（不含 decision / recommendation / approval / quote / pricing /
  engineering_approved 等决策键，红线③/⑥）。
- WorkflowAnalytics.insight 仅作 widget.note，不进入 facts。
- RiskDashboard 风险组件 requires_human_confirmation 恒为 True（红线③/⑥：AI 不判定）。
- 视图构建为纯只读装配，不持有任何批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
- 默认 visibility = "org"（由 AnalyticsVisibilityPolicy 进一步按角色过滤）。
"""

from __future__ import annotations

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.dashboard_views import (
    AIDashboard,
    ProjectDashboard,
    RiskDashboard,
    WorkflowDashboard,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.operation_risk import RiskCandidate, RiskSeverity
from agents.enterprise.project_analytics import ProjectAnalytics
from agents.enterprise.workflow_analytics import WorkflowAnalytics

_FORBIDDEN_FACT_KEYS = (
    "decision",
    "recommendation",
    "approval",
    "approved",
    "quote",
    "pricing",
    "engineering_approved",
)


def _assert_fact_only(dashboard) -> None:
    for w in dashboard.widgets:
        for key in w.facts:
            assert key not in _FORBIDDEN_FACT_KEYS, (
                f"widget {w.widget_id} 含决策性事实键 {key!r}：驾驶舱只展示事实"
            )


def _project_analytics() -> ProjectAnalytics:
    return ProjectAnalytics(
        org_id="org-1",
        total_projects=10,
        completed_count=4,
        completion_rate=0.4,
        avg_cycle_days=12.5,
        status_distribution={"active": 5, "done": 4, "paused": 1},
    )


def _workflow_analytics() -> WorkflowAnalytics:
    return WorkflowAnalytics(
        org_id="org-1",
        stage_duration={"design": 2.0, "review": 1.5},
        sla_status={"on_track": 3, "at_risk": 1},
        bottleneck="review",
        insight="review 阶段耗时最高，建议人工评估资源",  # 描述性，非决策
    )


def _ai_analytics() -> AIUsageAnalytics:
    return AIUsageAnalytics(
        org_id="org-1",
        total_calls=120,
        task_type_distribution={"design": 80, "review": 40},
        response_ok=118,
        response_fail=2,
        avg_response_time=0.8,
    )


def _risk_candidates() -> list[RiskCandidate]:
    return [
        RiskCandidate(risk_id="R1", org_id="org-1", risk_type="sla_overdue", severity=RiskSeverity.HIGH, evidence="x"),
        RiskCandidate(risk_id="R2", org_id="org-1", risk_type="quality", severity=RiskSeverity.MEDIUM, evidence="y"),
    ]


def test_project_dashboard_fact_only() -> None:
    d = ProjectDashboard(org_id="org-1").build(
        dashboard_id="PD", owner_id="u-1", analytics=_project_analytics()
    )
    assert d.org_id == "org-1"
    assert d.visibility == "org"
    assert len(d.widgets) == 4
    assert {w.widget_type.value for w in d.widgets} == {"metric", "table"}
    assert all(w.source == "project_analytics" for w in d.widgets)
    _assert_fact_only(d)


def test_workflow_dashboard_insight_as_note_not_fact() -> None:
    d = WorkflowDashboard(org_id="org-1").build(
        dashboard_id="WD", owner_id="u-1", analytics=_workflow_analytics()
    )
    assert len(d.widgets) == 3
    assert {w.widget_type.value for w in d.widgets} == {"chart", "table", "metric"}
    # insight 必须只出现在 note，不进入任何 facts
    assert any("review" in (w.note or "") for w in d.widgets)
    for w in d.widgets:
        assert "insight" not in w.facts
    _assert_fact_only(d)


def test_ai_dashboard_fact_only() -> None:
    d = AIDashboard(org_id="org-1").build(
        dashboard_id="AD", owner_id="u-1", analytics=_ai_analytics()
    )
    assert len(d.widgets) == 3
    assert all(w.source == "ai_usage_analytics" for w in d.widgets)
    _assert_fact_only(d)


def test_risk_dashboard_requires_human_confirmation_true() -> None:
    d = RiskDashboard(org_id="org-1").build(
        dashboard_id="RD", owner_id="u-1", candidates=_risk_candidates()
    )
    assert len(d.widgets) == 1
    w = d.widgets[0]
    assert w.widget_type.value == "risk"
    assert w.source == "operation_risk"
    risks = w.facts["risks"]
    assert len(risks) == 2
    # 红线③/⑥：风险候选必须保持 requires_human_confirmation=true，AI 不作判定
    assert all(r["requires_human_confirmation"] is True for r in risks)
    assert "人工确认" in (w.note or "")
    _assert_fact_only(d)


def test_views_hold_no_forbidden_methods() -> None:
    # 红线②/③/④/⑥：视图类不持有批准/报价/审批/记录为人工/决策方法
    forbidden = ("approve", "engineering_approved", "quote", "pricing", "sign",
                 "authorize", "record_human_approval")
    for cls in (ProjectDashboard, WorkflowDashboard, AIDashboard, RiskDashboard):
        inst = cls(org_id="org-1")
        for name in forbidden:
            assert not hasattr(inst, name), f"{cls.__name__} 意外持有 forbidden 方法 {name}"
