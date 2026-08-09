"""Enterprise Knowledge Governance & Version Control Layer —— 测试6：权限接入（Phase 3.8.8）。

覆盖（AnalyticsVisibilityPolicy / RoleKind）：
- 任务6 在 _ROLE_VISIBLE_SOURCES 新增 knowledge_view（查看治理事实，全员可见）与
  knowledge_manage（管理治理动作，仅 ADMIN / EXPERT / REVIEWER 可见）。
- 不同角色对 knowledge 数据源有不同的可见范围（默认拒绝）。
- is_source_permitted / can_view_dashboard 行为正确。
"""

from __future__ import annotations

import pytest

from agents.enterprise.dashboard import Dashboard, DashboardWidget
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.identity import RoleKind


def _policy(org_id: str = "org-1") -> AnalyticsVisibilityPolicy:
    return AnalyticsVisibilityPolicy(org_id=org_id)


@pytest.mark.parametrize(
    "role",
    [RoleKind.ADMIN, RoleKind.DESIGNER, RoleKind.ENGINEER, RoleKind.EXPERT, RoleKind.REVIEWER],
)
def test_knowledge_view_visible_to_all_roles(role: RoleKind) -> None:
    pol = _policy()
    # knowledge_view（查看版本/候选/审核/冲突等治理事实）对全部 5 类角色可见
    assert pol.is_source_permitted(role, "knowledge_view") is True


@pytest.mark.parametrize(
    "role",
    [RoleKind.ADMIN, RoleKind.EXPERT, RoleKind.REVIEWER],
)
def test_knowledge_manage_visible_to_privileged_roles(role: RoleKind) -> None:
    pol = _policy()
    assert pol.is_source_permitted(role, "knowledge_manage") is True


@pytest.mark.parametrize(
    "role",
    [RoleKind.DESIGNER, RoleKind.ENGINEER],
)
def test_knowledge_manage_hidden_from_non_privileged_roles(role: RoleKind) -> None:
    pol = _policy()
    # DESIGNER / ENGINEER 仅有 knowledge_view，无 knowledge_manage（默认拒绝）
    assert pol.is_source_permitted(role, "knowledge_manage") is False


def test_unknown_source_default_denied() -> None:
    pol = _policy()
    # 未在策略中的源默认拒绝（不裸奔放行）
    assert pol.is_source_permitted(RoleKind.ADMIN, "knowledge_secret") is False


def _dashboard_with_knowledge_widgets() -> Dashboard:
    widgets = [
        DashboardWidget(widget_id="w1", widget_type="table", title="t",
                        source="knowledge_manage"),
        DashboardWidget(widget_id="w2", widget_type="table", title="t",
                        source="knowledge_view"),
        DashboardWidget(widget_id="w3", widget_type="table", title="t",
                        source="project_analytics"),
    ]
    return Dashboard(
        dashboard_id="d1", org_id="org-1", owner_id="o",
        widgets=widgets, visibility="org",
    )


def test_can_view_dashboard_for_knowledge_widgets() -> None:
    pol = _policy()
    dash = _dashboard_with_knowledge_widgets()
    # ADMIN 可见全部 3 个组件（含 knowledge_manage + knowledge_view）
    admin_w = pol.visible_widgets(RoleKind.ADMIN, dash, "o")
    assert {w.widget_id for w in admin_w} == {"w1", "w2", "w3"}
    # DESIGNER 仅可见 knowledge_view + project_analytics（无 knowledge_manage）
    eng_w = pol.visible_widgets(RoleKind.DESIGNER, dash, "o")
    assert {w.widget_id for w in eng_w} == {"w2", "w3"}


def test_visible_widgets_respects_knowledge_sources() -> None:
    pol = _policy()
    widgets = [
        DashboardWidget(widget_id="w1", widget_type="table", title="t",
                        source="knowledge_view"),
        DashboardWidget(widget_id="w2", widget_type="table", title="t",
                        source="knowledge_manage"),
    ]
    dash = Dashboard(dashboard_id="d1", org_id="org-1", owner_id="o",
                     widgets=widgets, visibility="org")
    admin = pol.filter_dashboard(RoleKind.ADMIN, dash, "o")
    assert {w.source for w in admin.widgets} == {"knowledge_view", "knowledge_manage"}
    engineer = pol.filter_dashboard(RoleKind.ENGINEER, dash, "o")
    assert {w.source for w in engineer.widgets} == {"knowledge_view"}
