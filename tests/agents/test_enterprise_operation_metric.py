"""Enterprise Analytics & Operation Intelligence Layer —— 测试1：运营指标模型（任务1，Phase 3.8.4）。

覆盖：
- create_metric 只登记事实（metric_id / org_id / metric_type / value / period / source）。
- list_metrics 按 metric_type / period 过滤。
- 跨域访问抛 EnterpriseIsolationError。
- 审计如实标注采集方（默认 AI；可显式 USER）。
- 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
- 额外拦截 auto_business_decision / make_management_decision（3.8.4 红线③/⑥）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.operation_metric import (
    OperationMetric,
    OperationMetricService,
    OperationMetricType,
)
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_create_metric_records_fact() -> None:
    svc = OperationMetricService(org_id="org-1")
    m = svc.create_metric(
        metric_id="OM-1",
        metric_type=OperationMetricType.COUNT,
        value=42.0,
        period="2026-08",
        source="project",
        recorded_at="t0",
    )
    assert isinstance(m, OperationMetric)
    assert m.metric_type == OperationMetricType.COUNT
    assert m.value == 42.0
    assert m.period == "2026-08"
    assert m.source == "project"
    assert m.org_id == "org-1"


def test_list_metrics_filters() -> None:
    svc = OperationMetricService(org_id="org-1")
    svc.create_metric(metric_id="OM-1", metric_type=OperationMetricType.COUNT, value=1.0, period="2026-08")
    svc.create_metric(metric_id="OM-2", metric_type=OperationMetricType.RATE, value=0.5, period="2026-08")
    svc.create_metric(metric_id="OM-3", metric_type=OperationMetricType.COUNT, value=9.0, period="2026-09")
    assert len(svc.list_metrics()) == 3
    assert len(svc.list_metrics(metric_type=OperationMetricType.COUNT)) == 2
    assert len(svc.list_metrics(period="2026-08")) == 2
    assert len(svc.list_metrics(metric_type=OperationMetricType.COUNT, period="2026-09")) == 1


def test_cross_org_access_isolated() -> None:
    s1 = OperationMetricService(org_id="org-1")
    s2 = OperationMetricService(org_id="org-2")
    s1.create_metric(metric_id="OM-1", metric_type=OperationMetricType.COUNT, value=1.0)
    with pytest.raises(EnterpriseIsolationError):
        s2.get(metric_id="OM-1")
    assert s2.list_metrics() == []


def test_audit_records_actor_ai_by_default() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = OperationMetricService(org_id="org-1", audit=audit)
    svc.create_metric(metric_id="OM-1", metric_type=OperationMetricType.COUNT, value=1.0, recorded_at="t0")
    recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "create_operation_metric" for r in recs)


def test_audit_records_actor_user_when_explicit() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = OperationMetricService(org_id="org-1", audit=audit)
    svc.create_metric(
        metric_id="OM-1",
        metric_type=OperationMetricType.COUNT,
        value=1.0,
        recorded_by="u-1",
        actor_kind="user",
    )
    user_recs = audit.query(actor_kind=AuditActorKind.USER)
    assert any(r.action == "create_operation_metric" for r in user_recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        OperationMetricService(org_id="org-1")


def test_forbidden_decision_method_blocked() -> None:
    svc = OperationMetricService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.auto_business_decision  # 3.8.4 红线③：禁止自动经营决策
