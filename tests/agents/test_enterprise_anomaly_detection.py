"""Enterprise Data Intelligence & Decision Support Layer —— 测试3：AnomalyDetector（任务3，Phase 3.8.6）。

覆盖：
- detect_from_metrics / detect_from_workflow_analytics / detect_from_ai_usage_analytics /
  detect_from_dashboard 四种入口，输入均为事实型数据源。
- requires_human_confirmation 恒为 True（必须人工确认，红线③/⑥）。
- 禁止 resolve / mitigate / fix / close 处置入口（红线③/⑥：AI 只发现不处置）。
- 来源不可追溯禁止检测（任务5：禁 AI 创造无源数据）。
- 审计如实标注 record_anomaly_detection（actor 默认 AI，红线⑥）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.ai_usage_analytics import AIUsageAnalytics
from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.dashboard import Dashboard, DashboardWidget, WidgetType
from agents.enterprise.operation_metric import OperationMetric
from agents.enterprise.operation_risk import RiskSeverity
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.workflow_analytics import WorkflowAnalytics
from agents.enterprise.anomaly_detection import AnomalyCandidate, AnomalyDetector


def test_detect_from_metrics_flag_deviation() -> None:
    svc = AnomalyDetector(org_id="org-1")
    metrics = [
        OperationMetric(metric_id="M-1", org_id="org-1", metric_type="count", value=10.0, source="project_analytics"),
        OperationMetric(metric_id="M-2", org_id="org-1", metric_type="count", value=95.0, source="project_analytics"),
    ]
    cand = svc.detect_from_metrics(anomaly_id="A-1", metrics=metrics, baseline_value=10.0, threshold=0.2)
    assert cand.anomaly_id == "A-1"
    assert cand.requires_human_confirmation is True
    assert cand.severity in (RiskSeverity.HIGH, RiskSeverity.MEDIUM, RiskSeverity.LOW)
    assert cand.source_trace.source_metric == ["M-1", "M-2"]


def test_detect_from_workflow_analytics_flags_overdue() -> None:
    svc = AnomalyDetector(org_id="org-1")
    wa = WorkflowAnalytics(
        org_id="org-1",
        analytics_id="WA-1",
        stage_duration={"design": 100.0},
        sla_status={"overdue": 3, "warning": 0},
        bottleneck="design",
        insight="存在 3 条 SLA 已逾期",
    )
    cand = svc.detect_from_workflow_analytics(anomaly_id="A-2", analytics=wa)
    assert cand.requires_human_confirmation is True
    assert cand.severity == RiskSeverity.HIGH  # overdue>0 → HIGH
    assert cand.source_trace.source_workflow == ["WA-1"]


def test_detect_from_ai_usage_flags_fail_rate() -> None:
    svc = AnomalyDetector(org_id="org-1")
    aa = AIUsageAnalytics(
        org_id="org-1",
        analytics_id="AA-1",
        total_calls=100,
        response_ok=80,
        response_fail=20,
        avg_response_time=1.2,
    )
    cand = svc.detect_from_ai_usage_analytics(anomaly_id="A-3", analytics=aa, fail_rate_threshold=0.1)
    assert cand.requires_human_confirmation is True
    assert cand.severity in (RiskSeverity.HIGH, RiskSeverity.MEDIUM)
    assert "AA-1" in cand.source_trace.raw_refs


def test_detect_from_dashboard_scans_risk_widgets() -> None:
    svc = AnomalyDetector(org_id="org-1")
    d = Dashboard(
        dashboard_id="D-1", org_id="org-1", owner_id="u-1",
        widgets=[DashboardWidget("w1", WidgetType.RISK, "r", facts={"total": 1}, source="operation_risk")],
    )
    cand = svc.detect_from_dashboard(anomaly_id="A-4", dashboard=d)
    assert cand.requires_human_confirmation is True
    assert cand.source_trace.source_dashboard == ["D-1"]


def test_no_resolution_entrypoint() -> None:
    # 红线③/⑥：异常检测器不得提供任何处置入口。
    svc = AnomalyDetector(org_id="org-1")
    for name in ("resolve", "mitigate", "fix", "close", "auto_business_decision", "make_management_decision"):
        assert not hasattr(type(svc), name), f"{name} 不应作为真实方法存在"
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.resolve
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.fix


def test_construct_raises_without_trace() -> None:
    # 直接构造 AnomalyCandidate 且来源不可追溯必须抛红线违例（任务5）。
    with pytest.raises(EnterpriseRedLineViolationError):
        AnomalyCandidate(anomaly_id="Z", org_id="org-1", source_trace=None)


def test_audit_records_anomaly_detection() -> None:
    audit = AuditService(org_id="org-1")
    svc = AnomalyDetector(org_id="org-1", audit=audit)
    metrics = [OperationMetric(metric_id="M-1", org_id="org-1", metric_type="count", value=10.0)]
    svc.detect_from_metrics(anomaly_id="A-1", metrics=metrics, baseline_value=10.0)
    recs = audit.query(category=AuditActionCategory.ANOMALY_DETECTION)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_construct_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        AnomalyDetector(org_id="org-1")
