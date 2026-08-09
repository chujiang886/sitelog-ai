"""Enterprise Intelligence Dashboard Layer —— 测试1：Dashboard 模型与服务（任务1，Phase 3.8.5）。

覆盖：
- create_dashboard 登记事实型驾驶舱（固定字段 dashboard_id/org_id/owner_id/widgets/visibility/created_at）。
- add_widget / get_dashboard / list_dashboards / remove_widget。
- 跨域访问抛 EnterpriseIsolationError。
- 四个企业视图（Project/Workflow/AI/Risk）只读组合 analytics 事实，产出事实型 widget。
- 审计如实标注驾驶舱创建/组件追加（AI action）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.dashboard import (
    Dashboard,
    DashboardService,
    DashboardWidget,
    WidgetType,
)
from agents.enterprise.dashboard_views import (
    AIDashboard,
    ProjectDashboard,
    RiskDashboard,
    WorkflowDashboard,
)
from agents.enterprise.operation_risk import RiskCandidate, RiskSeverity
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.project_analytics import ProjectAnalytics
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_analytics import WorkflowAnalytics


def test_create_dashboard_fields() -> None:
    svc = DashboardService(org_id="org-1")
    d = svc.create_dashboard(dashboard_id="D-1", owner_id="u-1", visibility="org", created_at="t0")
    assert isinstance(d, Dashboard)
    assert d.dashboard_id == "D-1"
    assert d.org_id == "org-1"
    assert d.owner_id == "u-1"
    assert d.visibility == "org"
    assert d.created_at == "t0"
    assert d.widgets == []


def test_add_and_get_widget_scoped() -> None:
    svc = DashboardService(org_id="org-1")
    svc.create_dashboard(dashboard_id="D-1", owner_id="u-1")
    w = DashboardWidget(widget_id="w1", widget_type=WidgetType.METRIC, title="x", facts={"v": 1})
    svc.add_widget(dashboard_id="D-1", widget=w)
    got = svc.get_dashboard(dashboard_id="D-1")
    assert len(got.widgets) == 1
    assert got.widgets[0].widget_id == "w1"


def test_cross_org_dashboard_isolated() -> None:
    s1 = DashboardService(org_id="org-1")
    s2 = DashboardService(org_id="org-2")
    s1.create_dashboard(dashboard_id="D-1", owner_id="u-1")
    with pytest.raises(EnterpriseIsolationError):
        s2.get_dashboard(dashboard_id="D-1")
    assert s2.list_dashboards() == []


def test_remove_widget() -> None:
    svc = DashboardService(org_id="org-1")
    svc.create_dashboard(dashboard_id="D-1", owner_id="u-1")
    svc.add_widget(dashboard_id="D-1", widget=DashboardWidget("w1", WidgetType.METRIC, "x", facts={"v": 1}))
    svc.add_widget(dashboard_id="D-1", widget=DashboardWidget("w2", WidgetType.METRIC, "y", facts={"v": 2}))
    svc.remove_widget(dashboard_id="D-1", widget_id="w1")
    assert [w.widget_id for w in svc.get_dashboard(dashboard_id="D-1").widgets] == ["w2"]


# ---- 企业视图只读组合（任务3）----


def test_project_dashboard_builds_fact_widgets() -> None:
    pa = ProjectAnalytics(
        org_id="org-1",
        total_projects=10,
        completed_count=3,
        completion_rate=0.3,
        avg_cycle_days=12.5,
        status_distribution={"active": 7, "archived": 3},
    )
    d = ProjectDashboard(org_id="org-1").build(dashboard_id="PD", owner_id="u-1", analytics=pa)
    assert d.visibility == "org"
    assert {w.source for w in d.widgets} == {"project_analytics"}
    assert any(w.widget_type_value() == "metric" for w in d.widgets)
    assert any(w.widget_type_value() == "table" for w in d.widgets)


def test_workflow_dashboard_builds_fact_widgets() -> None:
    wa = WorkflowAnalytics(
        org_id="org-1",
        stage_duration={"design": 100.0, "review": 50.0},
        sla_status={"on_track": 5, "overdue": 2},
        bottleneck="design",
        insight="耗时最长的阶段为「design」",
    )
    d = WorkflowDashboard(org_id="org-1").build(dashboard_id="WD", owner_id="u-1", analytics=wa)
    assert {w.source for w in d.widgets} == {"workflow_analytics"}
    # insight 仅作为 note，不得进入 facts
    for w in d.widgets:
        assert "insight" not in w.facts


def test_ai_dashboard_builds_fact_widgets() -> None:
    aa = AIUsageAnalytics(
        org_id="org-1",
        total_calls=20,
        task_type_distribution={"design_consult": 12, "vision": 8},
        response_ok=18,
        response_fail=2,
        avg_response_time=1.5,
    )
    d = AIDashboard(org_id="org-1").build(dashboard_id="AD", owner_id="u-1", analytics=aa)
    assert {w.source for w in d.widgets} == {"ai_usage_analytics"}


def test_risk_dashboard_lists_candidates_requiring_human() -> None:
    cands = [
        RiskCandidate(risk_id="R1", org_id="org-1", risk_type="sla_overdue", severity=RiskSeverity.HIGH, evidence="x"),
        RiskCandidate(risk_id="R2", org_id="org-1", risk_type="low_completion", severity=RiskSeverity.MEDIUM, evidence="y"),
    ]
    d = RiskDashboard(org_id="org-1").build(dashboard_id="RD", owner_id="u-1", candidates=cands)
    assert {w.source for w in d.widgets} == {"operation_risk"}
    risk_widget = d.widgets[0]
    assert risk_widget.widget_type_value() == "risk"
    assert risk_widget.facts["total"] == 2
    assert all(r["requires_human_confirmation"] is True for r in risk_widget.facts["risks"])


# ---- 审计如实标注 ----


def test_audit_records_dashboard_create() -> None:
    from agents.enterprise.audit import AuditActionCategory, AuditService

    audit = AuditService(org_id="org-1")
    svc = DashboardService(org_id="org-1", audit=audit)
    svc.create_dashboard(dashboard_id="D-1", owner_id="u-1")
    recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "create_dashboard" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    import pytest

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        DashboardService(org_id="org-1")
