"""Enterprise Intelligence Dashboard Layer —— 测试3：可见性策略（任务4，Phase 3.8.5）。

覆盖：
- AnalyticsVisibilityPolicy 默认拒绝：角色未显式允许的源不可见。
- can_view_dashboard：private / org / role:<kind> 三种 visibility 叠加角色判定。
- filter_dashboard：返回仅含可见事实组件的副本（不修改原对象）。
- 未知 visibility 声明 → 默认拒绝（fail-closed）。
"""

from __future__ import annotations

from agents.enterprise.dashboard import Dashboard, DashboardWidget, WidgetType
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.identity import RoleKind


def _dash_with_sources(sources):  # type: ignore[no-untyped-def]
    widgets = [
        DashboardWidget(widget_id=f"w-{s}", widget_type=WidgetType.METRIC, title=s, facts={"v": 1}, source=s)
        for s in sources
    ]
    return Dashboard(dashboard_id="D", org_id="org-1", owner_id="u-1", widgets=widgets, visibility="org")


def test_default_deny_unlisted_source() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    # DESIGNER 未列 operation_risk → 不可见
    assert pol.is_source_permitted(RoleKind.DESIGNER, "operation_risk") is False
    # 空 source 视为通用 → 全部角色可见
    assert pol.is_source_permitted(RoleKind.DESIGNER, "") is True


def test_role_source_mapping() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    # EXPERT 可见 project + ai，不可见 workflow / risk
    assert pol.is_source_permitted(RoleKind.EXPERT, "project_analytics") is True
    assert pol.is_source_permitted(RoleKind.EXPERT, "ai_usage_analytics") is True
    assert pol.is_source_permitted(RoleKind.EXPERT, "workflow_analytics") is False
    # REVIEWER 可见 risk
    assert pol.is_source_permitted(RoleKind.REVIEWER, "operation_risk") is True


def test_can_view_private_only_owner() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    d = Dashboard(dashboard_id="D", org_id="org-1", owner_id="u-1", visibility="private")
    assert pol.can_view_dashboard(RoleKind.ADMIN, d, viewer_id="u-1") is True
    assert pol.can_view_dashboard(RoleKind.ADMIN, d, viewer_id="u-2") is False


def test_can_view_role_scoped() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    d = Dashboard(dashboard_id="D", org_id="org-1", owner_id="u-1", visibility="role:reviewer")
    assert pol.can_view_dashboard(RoleKind.REVIEWER, d, viewer_id="u-9") is True
    assert pol.can_view_dashboard(RoleKind.DESIGNER, d, viewer_id="u-9") is False


def test_can_view_unknown_visibility_denied() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    d = Dashboard(dashboard_id="D", org_id="org-1", owner_id="u-1", visibility="secret")
    assert pol.can_view_dashboard(RoleKind.ADMIN, d, viewer_id="u-1") is False


def test_filter_dashboard_returns_visible_only() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    d = _dash_with_sources(["project_analytics", "workflow_analytics", "operation_risk"])
    # DESIGNER 不可见 operation_risk
    filtered = pol.filter_dashboard(RoleKind.DESIGNER, d, viewer_id="u-1")
    visible_sources = {w.source for w in filtered.widgets}
    assert visible_sources == {"project_analytics", "workflow_analytics"}
    # 原对象不被修改
    assert {w.source for w in d.widgets} == {"project_analytics", "workflow_analytics", "operation_risk"}
