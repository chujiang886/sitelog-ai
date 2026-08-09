"""Enterprise Data Intelligence & Decision Support Layer —— 测试1：DataInsight（任务1 + 任务5，Phase 3.8.6）。

覆盖：
- create_insight 登记事实型洞察（字段 insight_id/org_id/source_data/pattern/confidence/
  description/requires_human_review/created_at/source_trace/source 齐全）。
- requires_human_review 恒为 True（AI 不代管理判断，红线③/⑥）。
- 来源不可追溯禁止登记（任务5：禁 AI 创造无源数据）。
- get / list_insights / query 组织隔离 + 读取。
- 审计如实标注 record_data_insight（actor 默认 AI，红线⑥）。
- 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.data_insight import DataInsight, DataInsightService, SourceTrace
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _trace() -> SourceTrace:
    return SourceTrace(source_metric=["M-1", "M-2"])


def test_create_insight_fields() -> None:
    svc = DataInsightService(org_id="org-1")
    ins = svc.create_insight(
        insight_id="I-1",
        source_data="2026-Q3 项目完成率指标",
        pattern="完成率环比上升",
        confidence=0.82,
        description="基于 M-1/M-2 的事实描述",
        source_trace=_trace(),
        source="project_analytics",
        created_at="t0",
    )
    assert ins.insight_id == "I-1"
    assert ins.org_id == "org-1"
    assert ins.pattern == "完成率环比上升"
    assert ins.confidence == 0.82
    assert ins.source == "project_analytics"
    assert ins.created_at == "t0"
    assert ins.source_trace.is_traceable


def test_requires_human_review_forced_true() -> None:
    svc = DataInsightService(org_id="org-1")
    # 即便未显式传 requires_human_review，__post_init__ 也强制置 True。
    ins = svc.create_insight(
        insight_id="I-1", source_data="d", pattern="p", confidence=0.5, source_trace=_trace(),
    )
    assert ins.requires_human_review is True

    # 直接构造 DataInsight 即便显式传 False 也会被强制 True。
    direct = DataInsight(
        insight_id="X", org_id="org-1", source_trace=_trace(), requires_human_review=False,
    )
    assert direct.requires_human_review is True


def test_untraceable_source_blocks_creation() -> None:
    svc = DataInsightService(org_id="org-1")
    # 空 SourceTrace（is_traceable=False）必须被拒绝。
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_insight(
            insight_id="I-2", source_data="d", pattern="p", confidence=0.5,
            source_trace=SourceTrace(),
        )
    # source_trace=None 也必须被拒绝。
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_insight(
            insight_id="I-3", source_data="d", pattern="p", confidence=0.5, source_trace=None,
        )


def test_construct_raises_without_trace() -> None:
    # 直接构造 DataInsight 且来源不可追溯必须抛红线违例（任务5）。
    with pytest.raises(EnterpriseRedLineViolationError):
        DataInsight(insight_id="Z", org_id="org-1", source_trace=SourceTrace())


def test_get_and_list_scoped() -> None:
    s1 = DataInsightService(org_id="org-1")
    s2 = DataInsightService(org_id="org-2")
    s1.create_insight(insight_id="I-1", source_data="d", pattern="p", confidence=0.5, source_trace=_trace(), source="project_analytics")
    with pytest.raises(EnterpriseIsolationError):
        s2.get(insight_id="I-1")
    assert s2.list_insights() == []
    got = s1.get(insight_id="I-1")
    assert got.insight_id == "I-1"


def test_query_by_source_and_pattern() -> None:
    svc = DataInsightService(org_id="org-1")
    svc.create_insight(insight_id="I-1", source_data="d", pattern="完成率上升", confidence=0.5, source_trace=_trace(), source="project_analytics")
    svc.create_insight(insight_id="I-2", source_data="d", pattern="调用量下降", confidence=0.5, source_trace=SourceTrace(source_event=["E-1"]), source="ai_usage_analytics")
    assert len(svc.query(source="ai_usage_analytics")) == 1
    assert len(svc.query(pattern_contains="上升")) == 1
    assert len(svc.query(pattern_contains="X不存在")) == 0


def test_audit_records_data_insight() -> None:
    audit = AuditService(org_id="org-1")
    svc = DataInsightService(org_id="org-1", audit=audit)
    svc.create_insight(insight_id="I-1", source_data="d", pattern="p", confidence=0.5, source_trace=_trace(), source="project_analytics")
    recs = audit.query(category=AuditActionCategory.DATA_INSIGHT)
    assert len(recs) == 1
    assert recs[0].action == "create_data_insight"
    assert recs[0].actor_kind == AuditActorKind.AI  # AI 生成记 AI（红线⑥）


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        DataInsightService(org_id="org-1")
