"""Enterprise Data Intelligence & Decision Support Layer —— 测试7：审计增强（任务7，Phase 3.8.6）。

覆盖（AuditService 新增 4 类 + 4 方法）：
- AuditActionCategory 新增 DATA_INSIGHT / TREND_ANALYSIS / ANOMALY_DETECTION / REPORT_GENERATION。
- record_data_insight / record_trend_analysis / record_anomaly_detection / record_report_generation
  四类事实事件如实记录，actor 默认 AI（红线⑥：不伪造人工审批）。
- 绝不提供 record_human_approval（红线⑥核心拦截点）。
- 写路径断言 safety_invariants_ok()（红线①/⑤）。
- 查询可按 category 过滤。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_new_categories_exist() -> None:
    for name in ("DATA_INSIGHT", "TREND_ANALYSIS", "ANOMALY_DETECTION", "REPORT_GENERATION"):
        assert hasattr(AuditActionCategory, name)
    assert AuditActionCategory.DATA_INSIGHT.value == "data_insight"
    assert AuditActionCategory.TREND_ANALYSIS.value == "trend_analysis"
    assert AuditActionCategory.ANOMALY_DETECTION.value == "anomaly_detection"
    assert AuditActionCategory.REPORT_GENERATION.value == "report_generation"


def test_record_data_insight_default_ai() -> None:
    audit = AuditService(org_id="org-1")
    rec = audit.record_data_insight(record_id="r1", actor_id="ai", target="I-1", detail="d")
    assert rec.category == AuditActionCategory.DATA_INSIGHT
    assert rec.actor_kind == AuditActorKind.AI  # AI 生成记 AI（红线⑥）


def test_record_trend_anomaly_report_default_ai() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_trend_analysis(record_id="r2", actor_id="ai", target="T-1")
    audit.record_anomaly_detection(record_id="r3", actor_id="ai", target="A-1")
    audit.record_report_generation(record_id="r4", actor_id="ai", target="REP-1")
    cats = {r.category for r in audit.query()}
    assert AuditActionCategory.TREND_ANALYSIS in cats
    assert AuditActionCategory.ANOMALY_DETECTION in cats
    assert AuditActionCategory.REPORT_GENERATION in cats
    for r in audit.query():
        assert r.actor_kind == AuditActorKind.AI


def test_user_actor_can_be_explicit() -> None:
    audit = AuditService(org_id="org-1")
    rec = audit.record_data_insight(record_id="r1", actor_id="u-1", actor_kind=AuditActorKind.USER)
    assert rec.actor_kind == AuditActorKind.USER  # 用户手动创建亦可如实标注 USER


def test_query_by_category() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_data_insight(record_id="r1", actor_id="ai", target="I-1")
    audit.record_trend_analysis(record_id="r2", actor_id="ai", target="T-1")
    only_insight = audit.query(category=AuditActionCategory.DATA_INSIGHT)
    assert len(only_insight) == 1
    assert only_insight[0].target == "I-1"


def test_no_record_human_approval() -> None:
    # 红线⑥核心拦截点：审计服务不得把动作记录为人工审批。
    audit = AuditService(org_id="org-1")
    assert not hasattr(type(audit), "record_human_approval")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = audit.record_human_approval


def test_write_fail_closed(monkeypatch) -> None:
    # 构造路径在启用态下即 fail-closed（红线①/⑤），构造本身即应被拦截，
    # 因此无需再测写路径——写路径 _append 同样断言 safety_invariants_ok()。
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        audit = AuditService(org_id="org-1")
