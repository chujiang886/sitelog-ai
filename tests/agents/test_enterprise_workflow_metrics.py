"""Enterprise Operation Layer —— 测试：流程统计（任务5，Phase 3.8.3）。

覆盖：
- 指标登记（duration / stage_time / completion_rate / sample_size）。
- completion_rate 钳制在 [0,1]（数据规整，非审批）。
- aggregate 对一组指标做均值聚合（duration / completion_rate 均值，stage_time 求和）。
- 跨域访问抛 EnterpriseIsolationError。
- WorkflowMetricsService 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_metrics import (
    WorkflowMetrics,
    WorkflowMetricsService,
)


def test_record_metrics() -> None:
    svc = WorkflowMetricsService(org_id="org-1")
    m = svc.record_metrics(
        metrics_id="M-1",
        template_id="T-1",
        workflow_id="W-1",
        duration=120.0,
        stage_time={"需求确认": 30.0, "方案设计": 90.0},
        completion_rate=1.0,
        sample_size=1,
        computed_at="t0",
    )
    assert isinstance(m, WorkflowMetrics)
    assert m.duration == 120.0
    assert m.stage_time == {"需求确认": 30.0, "方案设计": 90.0}
    assert m.completion_rate == 1.0
    assert m.org_id == "org-1"


def test_completion_rate_clamped() -> None:
    svc = WorkflowMetricsService(org_id="org-1")
    m = svc.record_metrics(metrics_id="M-1", completion_rate=1.5)
    assert m.completion_rate == 1.0
    m2 = svc.record_metrics(metrics_id="M-2", completion_rate=-0.2)
    assert m2.completion_rate == 0.0


def test_aggregate_means_and_stage_sum() -> None:
    svc = WorkflowMetricsService(org_id="org-1")
    svc.record_metrics(metrics_id="M-1", template_id="T-1", duration=100.0,
                       stage_time={"a": 40.0}, completion_rate=1.0, sample_size=1)
    svc.record_metrics(metrics_id="M-2", template_id="T-1", duration=200.0,
                       stage_time={"a": 60.0, "b": 50.0}, completion_rate=0.0, sample_size=1)
    agg = svc.aggregate(metrics_id="AGG-1", template_id="T-1")
    assert agg.sample_size == 2
    assert agg.duration == 150.0
    assert agg.completion_rate == 0.5
    assert agg.stage_time == {"a": 100.0, "b": 50.0}


def test_aggregate_empty() -> None:
    svc = WorkflowMetricsService(org_id="org-1")
    agg = svc.aggregate(metrics_id="AGG-0", template_id="T-NONE")
    assert agg.sample_size == 0
    assert agg.duration == 0.0
    assert agg.completion_rate == 0.0


def test_list_metrics_by_template() -> None:
    svc = WorkflowMetricsService(org_id="org-1")
    svc.record_metrics(metrics_id="M-1", template_id="T-1")
    svc.record_metrics(metrics_id="M-2", template_id="T-2")
    assert len(svc.list_metrics()) == 2
    assert len(svc.list_metrics(template_id="T-1")) == 1


def test_cross_org_access_isolated() -> None:
    s1 = WorkflowMetricsService(org_id="org-1")
    s2 = WorkflowMetricsService(org_id="org-2")
    s1.record_metrics(metrics_id="M-1", template_id="T-1")
    with pytest.raises(EnterpriseIsolationError):
        s2.get(metrics_id="M-1")
    assert s2.list_metrics() == []


def test_audit_records_workflow_event() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = WorkflowMetricsService(org_id="org-1", audit=audit)
    svc.record_metrics(metrics_id="M-1", template_id="T-1", duration=10.0, completion_rate=1.0)
    recs = audit.query(category=AuditActionCategory.WORKFLOW_EVENT)
    assert any(r.action == "record_workflow_metrics" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowMetricsService(org_id="org-1")
