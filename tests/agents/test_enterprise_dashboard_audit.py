"""Enterprise Intelligence Dashboard Layer —— 测试5：驾驶舱审计（任务5，Phase 3.8.5）。

覆盖：
- record_dashboard_view / record_dashboard_query / record_dashboard_export 记录 DASHBOARD 类别。
- 这些动作**如实标注 actor**（默认 USER），绝不伪造人工审批（红线⑥）。
- DashboardService.render_dashboard / run_query / export_dashboard 触发对应审计。
- record_human_approval 仍被拦截（红线⑥：禁止把动作记录为人工审批）。
- Dashboard 审计与既有 AI_ACTION / USER_ACTION 类别互不串类。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.dashboard import (
    DashboardService,
    DashboardWidget,
    WidgetType,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc_with_audit() -> tuple[DashboardService, AuditService]:
    audit = AuditService(org_id="org-1")
    svc = DashboardService(org_id="org-1", audit=audit)
    svc.create_dashboard(dashboard_id="D-1", owner_id="u-1")
    svc.add_widget(
        dashboard_id="D-1",
        widget=DashboardWidget(widget_id="w1", widget_type=WidgetType.METRIC, title="x", facts={"v": 1}),
    )
    return svc, audit


def test_dashboard_view_audit_recorded() -> None:
    svc, audit = _svc_with_audit()
    svc.render_dashboard(dashboard_id="D-1", viewer_id="u-viewer", ts="t1")
    recs = audit.query(category=AuditActionCategory.DASHBOARD)
    assert any(r.action == "dashboard_view" for r in recs)
    assert recs[0].actor_kind == AuditActorKind.USER


def test_dashboard_query_audit_recorded() -> None:
    svc, audit = _svc_with_audit()
    svc.run_query(dashboard_id="D-1", query="status", viewer_id="u-viewer", ts="t2")
    recs = audit.query(category=AuditActionCategory.DASHBOARD)
    assert any(r.action == "dashboard_query" for r in recs)


def test_dashboard_export_audit_recorded() -> None:
    svc, audit = _svc_with_audit()
    svc.export_dashboard(dashboard_id="D-1", fmt="csv", viewer_id="u-viewer", ts="t3")
    recs = audit.query(category=AuditActionCategory.DASHBOARD)
    assert any(r.action == "dashboard_export" for r in recs)


def test_dashboard_audit_not_faked_as_human_approval() -> None:
    audit = AuditService(org_id="org-1")
    # 红线⑥：record_human_approval 结构性不可达
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = audit.record_human_approval  # type: ignore[attr-defined]


def test_dashboard_audit_category_isolated_from_other_categories() -> None:
    svc, audit = _svc_with_audit()
    svc.render_dashboard(dashboard_id="D-1", viewer_id="u-viewer")
    dash = audit.query(category=AuditActionCategory.DASHBOARD)
    ai = audit.query(category=AuditActionCategory.AI_ACTION)
    assert len(dash) == 1
    # AI_ACTION 仅含 create_dashboard / add_dashboard_widget（构建期），不含 view
    assert all(r.action != "dashboard_view" for r in ai)


def test_dashboard_audit_actor_can_be_explicit_ai() -> None:
    svc, audit = _svc_with_audit()
    svc.render_dashboard(dashboard_id="D-1", viewer_id="ai-render", actor_kind="ai")
    recs = audit.query(category=AuditActionCategory.DASHBOARD)
    assert recs[0].actor_kind == AuditActorKind.AI
