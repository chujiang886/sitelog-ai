"""Enterprise Data Intelligence & Decision Support Layer —— 测试6：权限级 source 可见性（任务6，Phase 3.8.6）。

覆盖（复用 3.8.1 IdentityService + 3.8.5 AnalyticsVisibilityPolicy）：
- DataInsightService.list_insights(role=...) 按角色级 source 可见性过滤洞察。
- AnalyticsVisibilityPolicy 默认拒绝：EXPERT 仅可见 project_analytics + ai_usage_analytics；
  DESIGNER/ENGINEER 不含 operation_risk；REVIEWER 含 operation_risk；ADMIN 全可见。
- 真实权限（view_*）仍由 identity 层校验，本策略仅为「展示层」细化（不授予权限）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.data_insight import DataInsightService, SourceTrace
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc() -> DataInsightService:
    svc = DataInsightService(
        org_id="org-1",
        identity=IdentityService(org_id="org-1"),
        visibility=AnalyticsVisibilityPolicy(org_id="org-1"),
    )
    svc.create_insight(insight_id="I-proj", source_data="d", pattern="p", confidence=0.5,
                       source_trace=SourceTrace(source_metric=["M-1"]), source="project_analytics")
    svc.create_insight(insight_id="I-ai", source_data="d", pattern="p", confidence=0.5,
                       source_trace=SourceTrace(source_event=["E-1"]), source="ai_usage_analytics")
    svc.create_insight(insight_id="I-risk", source_data="d", pattern="p", confidence=0.5,
                       source_trace=SourceTrace(source_dashboard=["D-1"]), source="operation_risk")
    return svc


def test_admin_sees_all_sources() -> None:
    svc = _svc()
    out = svc.list_insights(role=RoleKind.ADMIN)
    assert {i.source for i in out} == {"project_analytics", "ai_usage_analytics", "operation_risk"}


def test_expert_only_project_and_ai_usage() -> None:
    svc = _svc()
    out = svc.list_insights(role=RoleKind.EXPERT)
    assert {i.source for i in out} == {"project_analytics", "ai_usage_analytics"}
    assert all(i.source != "operation_risk" for i in out)


def test_designer_excludes_operation_risk() -> None:
    svc = _svc()
    out = svc.list_insights(role=RoleKind.DESIGNER)
    assert "operation_risk" not in {i.source for i in out}


def test_reviewer_includes_operation_risk() -> None:
    svc = _svc()
    out = svc.list_insights(role=RoleKind.REVIEWER)
    assert "operation_risk" in {i.source for i in out}


def test_no_role_sees_everything() -> None:
    # 不传 role → 不做角色过滤（仅组织隔离）。
    svc = _svc()
    assert len(svc.list_insights()) == 3


def test_visibility_policy_default_deny_unknown_source() -> None:
    pol = AnalyticsVisibilityPolicy(org_id="org-1")
    # 未知 source 对全部角色默认不可见（fail-closed）。
    assert pol.is_source_permitted(RoleKind.ADMIN, "unknown_source") is False
    # 空 source 视为通用组件，对全部角色可见。
    assert pol.is_source_permitted(RoleKind.EXPERT, "") is True


def test_construct_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        _svc()
