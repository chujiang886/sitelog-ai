"""Enterprise Intelligence Dashboard Layer —— 测试4：分析权限（角色级数据可见性，Phase 3.8.5）。

覆盖（任务4 落地校验）：
- 同一组驾驶舱事实，不同角色经 AnalyticsVisibilityPolicy 过滤后**看到不同数据**。
- DESIGNER 不可见 operation_risk（风险）源；REVIEWER 可见。
- EXPERT 不可见 workflow_analytics 源；DESIGNER 可见。
- 角色策略与 Dashboard.visibility 叠加后仍正确。
"""

from __future__ import annotations

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.dashboard_views import (
    AIDashboard,
    RiskDashboard,
    WorkflowDashboard,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.operation_risk import RiskCandidate, RiskSeverity
from agents.enterprise.workflow_analytics import WorkflowAnalytics


def _risk_dash() -> object:
    cands = [RiskCandidate(risk_id="R1", org_id="org-1", risk_type="sla_overdue", severity=RiskSeverity.HIGH, evidence="x")]
    return RiskDashboard(org_id="org-1").build(dashboard_id="RD", owner_id="u-1", candidates=cands)


def _wf_dash() -> object:
    wa = WorkflowAnalytics(org_id="org-1", stage_duration={"design": 1.0}, sla_status={"on_track": 1})
    return WorkflowDashboard(org_id="org-1").build(dashboard_id="WD", owner_id="u-1", analytics=wa)


def _ai_dash() -> object:
    aa = AIUsageAnalytics(org_id="org-1", total_calls=5)
    return AIDashboard(org_id="org-1").build(dashboard_id="AD", owner_id="u-1", analytics=aa)


def test_designer_cannot_see_risk_but_reviewer_can() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    rd = _risk_dash()
    designer = pol.filter_dashboard(RoleKind.DESIGNER, rd, viewer_id="u-1")  # type: ignore[arg-type]
    reviewer = pol.filter_dashboard(RoleKind.REVIEWER, rd, viewer_id="u-1")  # type: ignore[arg-type]
    assert designer.widgets == []  # DESIGNER 看不到风险源
    assert len(reviewer.widgets) == 1  # REVIEWER 看得到


def test_expert_cannot_see_workflow_but_designer_can() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    wd = _wf_dash()
    expert = pol.filter_dashboard(RoleKind.EXPERT, wd, viewer_id="u-1")  # type: ignore[arg-type]
    designer = pol.filter_dashboard(RoleKind.DESIGNER, wd, viewer_id="u-1")  # type: ignore[arg-type]
    assert expert.widgets == []  # EXPERT 看不到 workflow 源
    assert len(designer.widgets) == 3  # DESIGNER 看得到全部 workflow 组件


def test_all_roles_see_ai_usage() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    ad = _ai_dash()
    for role in (RoleKind.ADMIN, RoleKind.DESIGNER, RoleKind.ENGINEER, RoleKind.EXPERT, RoleKind.REVIEWER):
        filtered = pol.filter_dashboard(role, ad, viewer_id="u-1")  # type: ignore[arg-type]
        assert len(filtered.widgets) == 3


def test_private_dashboard_role_filter_still_respects_owner() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    cands = [RiskCandidate(risk_id="R1", org_id="org-1", risk_type="x", severity=RiskSeverity.LOW, evidence="e")]
    rd = RiskDashboard(org_id="org-1").build(dashboard_id="RD", owner_id="u-owner", candidates=cands)
    rd.visibility = "private"
    # 非 owner 即便角色 permitted，整体仍不可见
    non_owner = pol.filter_dashboard(RoleKind.REVIEWER, rd, viewer_id="u-stranger")  # type: ignore[arg-type]
    assert non_owner.widgets == []
    # owner 可见
    owner = pol.filter_dashboard(RoleKind.REVIEWER, rd, viewer_id="u-owner")  # type: ignore[arg-type]
    assert len(owner.widgets) == 1
