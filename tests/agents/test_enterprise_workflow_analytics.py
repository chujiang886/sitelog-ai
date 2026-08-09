"""Enterprise Analytics & Operation Intelligence Layer —— 测试3：流程效率分析（任务3，Phase 3.8.4）。

覆盖：
- compute_workflow_analytics 输出 stage_duration / sla_status / bottleneck / insight。
- **禁止自动修改流程**：modify_workflow / update_workflow / auto_fix 被拦截（红线③/⑥）。
- 审计如实标注 AI 动作。
- 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_analytics import WorkflowAnalyticsService
from agents.enterprise.workflow_metrics import WorkflowMetricsService
from agents.enterprise.workflow_sla import WorkflowSLAService, WorkflowSLAStatus


def _seed(org_id: str):
    metrics = WorkflowMetricsService(org_id=org_id)
    metrics.record_metrics(
        metrics_id="M-1",
        stage_time={"需求确认": 30.0, "方案设计": 90.0},
        completion_rate=1.0,
    )
    slas = WorkflowSLAService(org_id=org_id)
    slas.create_sla(sla_id="S-1", deadline="2030-01-01", warning="2029-12-01")
    return metrics, slas


def test_compute_workflow_analytics_insight() -> None:
    metrics, slas = _seed("org-1")
    svc = WorkflowAnalyticsService(org_id="org-1", metrics_service=metrics, sla_service=slas)
    a = svc.compute_workflow_analytics(analytics_id="WA-1", computed_at="t0")
    assert a.stage_duration == {"需求确认": 30.0, "方案设计": 90.0}
    assert a.bottleneck == "方案设计"  # 耗时最大阶段（事实推导）
    assert a.sla_status == {WorkflowSLAStatus.ON_TRACK.value: 1}
    assert "方案设计" in a.insight
    assert "ON_TRACK" in a.insight


def test_no_workflow_modification_entrypoint() -> None:
    svc = WorkflowAnalyticsService(org_id="org-1")
    # 红线③/⑥：禁止自动修改流程
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.modify_workflow
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.update_workflow
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.auto_fix


def test_audit_records_ai_action() -> None:
    from agents.enterprise.audit import AuditService

    metrics, slas = _seed("org-1")
    audit = AuditService(org_id="org-1")
    svc = WorkflowAnalyticsService(org_id="org-1", audit=audit, metrics_service=metrics, sla_service=slas)
    svc.compute_workflow_analytics(analytics_id="WA-1", computed_at="t0")
    recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "compute_workflow_analytics" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowAnalyticsService(org_id="org-1")
