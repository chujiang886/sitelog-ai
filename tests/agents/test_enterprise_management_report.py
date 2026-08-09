"""Enterprise Data Intelligence & Decision Support Layer —— 测试4：ManagementReport（任务4，Phase 3.8.6）。

覆盖：
- generate_report 把事实型洞察/趋势/异常/风险**汇编**为管理报告（仅汇总事实）。
- 禁止经营建议/管理决策/执行方案（红线③/⑥：无 recommend/decide/
  make_management_decision/optimize_business_strategy 入口）。
- 来源聚合可溯源（任务5：空输入 / 聚合不可追溯均拒绝）。
- 审计如实标注 record_report_generation（actor 默认 AI，红线⑥）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.data_insight import DataInsight, SourceTrace
from agents.enterprise.operation_risk import RiskCandidate, RiskSeverity
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.trend_analysis import TrendInsight
from agents.enterprise.anomaly_detection import AnomalyCandidate
from agents.enterprise.management_report import ManagementReport, ManagementReportService


def _insight() -> DataInsight:
    return DataInsight(
        insight_id="I-1", org_id="org-1", source_data="d", pattern="p",
        confidence=0.5, source_trace=SourceTrace(source_metric=["M-1"]), source="project_analytics",
    )


def _trend() -> TrendInsight:
    return TrendInsight(
        trend_id="T-1", org_id="org-1", change_pattern="increase", confidence=0.5,
        source_trace=SourceTrace(source_workflow=["W-1"]), source="workflow_analytics",
    )


def _anomaly() -> AnomalyCandidate:
    return AnomalyCandidate(
        anomaly_id="A-1", org_id="org-1", pattern="dev", severity=RiskSeverity.MEDIUM,
        evidence="e", source_trace=SourceTrace(source_event=["E-1"]), source="ai_usage_analytics",
    )


def _risk() -> RiskCandidate:
    return RiskCandidate(risk_id="R-1", org_id="org-1", risk_type="sla_overdue", evidence="x")


def test_generate_report_assembles_facts() -> None:
    svc = ManagementReportService(org_id="org-1")
    rep = svc.generate_report(
        report_id="REP-1", period="2026-Q3",
        insights=[_insight()], trends=[_trend()], anomalies=[_anomaly()], risks=[_risk()],
    )
    assert rep.report_id == "REP-1"
    assert rep.period == "2026-Q3"
    assert rep.facts == ["I-1"]
    assert rep.trends == ["T-1"]
    assert set(rep.risks) == {"A-1", "R-1"}
    # 来源聚合可溯源：合并了 metric/workflow/event 三类。
    assert rep.source_trace.is_traceable


def test_empty_report_rejected() -> None:
    svc = ManagementReportService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.generate_report(report_id="REP-2")


def test_construct_raises_without_trace() -> None:
    # 直接构造 ManagementReport 且来源不可追溯必须抛红线违例（任务5）。
    with pytest.raises(EnterpriseRedLineViolationError):
        ManagementReport(report_id="Z", org_id="org-1", source_trace=SourceTrace())


def test_no_management_decision_entrypoint() -> None:
    # 红线③/⑥：管理报告服务不得提供任何经营决策/建议入口。
    svc = ManagementReportService(org_id="org-1")
    for name in ("make_management_decision", "recommend_management_action",
                 "optimize_business_strategy", "execute_strategy", "recommend", "decide"):
        assert not hasattr(type(svc), name), f"{name} 不应作为真实方法存在"
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.make_management_decision
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.recommend


def test_audit_records_report_generation() -> None:
    audit = AuditService(org_id="org-1")
    svc = ManagementReportService(org_id="org-1", audit=audit)
    svc.generate_report(report_id="REP-1", insights=[_insight()], trends=[_trend()])
    recs = audit.query(category=AuditActionCategory.REPORT_GENERATION)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_construct_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        ManagementReportService(org_id="org-1")
