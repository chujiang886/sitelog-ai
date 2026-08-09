"""Enterprise Data Intelligence & Decision Support Layer —— 测试5：来源追踪 SourceTrace（任务5，Phase 3.8.6）。

覆盖：
- SourceTrace.is_traceable 四种溯源键（source_metric / source_workflow / source_event /
  source_dashboard）任一即视为可溯源；全空不可溯源。
- DataInsight / TrendInsight / AnomalyCandidate / ManagementReport 四类对象均强制要求
  source_trace.is_traceable（任务5：禁 AI 创造无源数据，红线③/⑥）。
- ManagementReport 聚合多个 SourceTrace 后必须仍可溯源（空聚合拒绝）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.anomaly_detection import AnomalyCandidate
from agents.enterprise.data_insight import DataInsight, SourceTrace
from agents.enterprise.management_report import ManagementReport, _merge_trace
from agents.enterprise.operation_risk import RiskSeverity
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.trend_analysis import TrendInsight


def test_is_traceable_variants() -> None:
    assert SourceTrace().is_traceable is False
    assert SourceTrace(source_metric=["M-1"]).is_traceable is True
    assert SourceTrace(source_workflow=["W-1"]).is_traceable is True
    assert SourceTrace(source_event=["E-1"]).is_traceable is True
    assert SourceTrace(source_dashboard=["D-1"]).is_traceable is True
    assert SourceTrace(raw_refs=["x-1"]).is_traceable is True


def test_insight_requires_traceable() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        DataInsight(insight_id="I", org_id="org-1", source_trace=SourceTrace())


def test_trend_requires_traceable() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        TrendInsight(trend_id="T", org_id="org-1", source_trace=SourceTrace())


def test_anomaly_requires_traceable() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AnomalyCandidate(anomaly_id="A", org_id="org-1", source_trace=SourceTrace())


def test_report_requires_traceable() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        ManagementReport(report_id="R", org_id="org-1", source_trace=SourceTrace())


def test_merge_trace_dedup_and_union() -> None:
    merged = _merge_trace([
        SourceTrace(source_metric=["M-1", "M-2"]),
        SourceTrace(source_metric=["M-2", "M-3"], source_event=["E-1"]),
        SourceTrace(),  # 空 trace 不参与
    ])
    assert merged.source_metric == ["M-1", "M-2", "M-3"]
    assert merged.source_event == ["E-1"]
    assert merged.is_traceable


def test_report_from_merged_trace_is_traceable() -> None:
    merged = _merge_trace([
        SourceTrace(source_metric=["M-1"]),
        SourceTrace(source_workflow=["W-1"]),
    ])
    rep = ManagementReport(report_id="R", org_id="org-1", source_trace=merged)
    assert rep.source_trace.is_traceable
    assert rep.source_trace.source_metric == ["M-1"]
    assert rep.source_trace.source_workflow == ["W-1"]


def test_merge_of_empty_traces_not_traceable() -> None:
    merged = _merge_trace([SourceTrace(), SourceTrace()])
    assert merged.is_traceable is False
    with pytest.raises(EnterpriseRedLineViolationError):
        ManagementReport(report_id="R", org_id="org-1", source_trace=merged)
