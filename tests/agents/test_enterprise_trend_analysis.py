"""Enterprise Data Intelligence & Decision Support Layer —— 测试2：TrendAnalyzer（任务2，Phase 3.8.6）。

覆盖：
- time_series_analysis / detect_change / compare_period 三种分析入口。
- 三者均只**描述**变化（change_pattern），不提供 optimize/improve 等处置入口（红线③/⑥）。
- requires_human_review 恒为 True。
- 来源不可追溯禁止分析（任务5：禁 AI 创造无源数据）。
- 审计如实标注 record_trend_analysis（actor 默认 AI，红线⑥）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.operation_metric import OperationMetric
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.trend_analysis import TrendAnalyzer, TrendInsight


def _metrics() -> list[OperationMetric]:
    return [
        OperationMetric(metric_id="M-1", org_id="org-1", metric_type="count", value=10.0, source="project_analytics"),
        OperationMetric(metric_id="M-2", org_id="org-1", metric_type="count", value=15.0, source="project_analytics"),
        OperationMetric(metric_id="M-3", org_id="org-1", metric_type="count", value=20.0, source="project_analytics"),
    ]


def test_time_series_analysis_describes_only() -> None:
    svc = TrendAnalyzer(org_id="org-1")
    t = svc.time_series_analysis(trend_id="T-1", metrics=_metrics(), period="2026-Q3", source="project_analytics")
    assert t.change_pattern.startswith("increase")
    assert t.requires_human_review is True
    assert t.source_trace.is_traceable
    assert t.source_trace.source_metric == ["M-1", "M-2", "M-3"]


def test_detect_change_requires_traceable_source() -> None:
    svc = TrendAnalyzer(org_id="org-1")
    # source_trace 不可追溯 → 拒绝。
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.detect_change(
            trend_id="T-2",
            series=[1.0, 2.0, 5.0],
            source_trace=SourceTrace(),
        )
    t = svc.detect_change(
        trend_id="T-2",
        series=[1.0, 2.0, 5.0],
        source_trace=SourceTrace(source_event=["E-9"]),
        threshold=0.1,
    )
    assert "change_point" in t.change_pattern
    assert t.requires_human_review is True


def test_compare_period_describes_only() -> None:
    svc = TrendAnalyzer(org_id="org-1")
    t = svc.compare_period(
        trend_id="T-3",
        current=[10.0, 12.0, 14.0],
        previous=[8.0, 9.0, 9.5],
        source_trace=SourceTrace(source_workflow=["W-1"]),
        period="2026-Q3",
    )
    assert "period_over_period" in t.change_pattern
    assert "increase" in t.change_pattern
    assert t.requires_human_review is True


def test_no_optimization_entrypoint() -> None:
    # 红线③/⑥：趋势分析器不得提供任何优化/改进入口。
    svc = TrendAnalyzer(org_id="org-1")
    for name in ("optimize", "improve", "auto_business_decision", "make_management_decision"):
        assert not hasattr(type(svc), name), f"{name} 不应作为真实方法存在"
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.optimize
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.improve


def test_cross_org_metric_rejected() -> None:
    from agents.enterprise.organization import EnterpriseIsolationError

    svc = TrendAnalyzer(org_id="org-1")
    foreign = [
        OperationMetric(metric_id="MX", org_id="org-2", metric_type="count", value=1.0),
    ]
    with pytest.raises(EnterpriseIsolationError):
        svc.time_series_analysis(trend_id="T-X", metrics=foreign)


def test_audit_records_trend_analysis() -> None:
    audit = AuditService(org_id="org-1")
    svc = TrendAnalyzer(org_id="org-1", audit=audit)
    svc.time_series_analysis(trend_id="T-1", metrics=_metrics(), source="project_analytics")
    recs = audit.query(category=AuditActionCategory.TREND_ANALYSIS)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_construct_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        TrendAnalyzer(org_id="org-1")
