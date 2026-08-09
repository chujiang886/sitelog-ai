"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试5：审计增强（任务5，Phase 3.8.7）。

覆盖（AuditService 新增 3 类 + 3 方法 + require_human_actor 守卫）：
- AuditActionCategory 新增 FEEDBACK / KNOWLEDGE_CANDIDATE / VALIDATION。
- record_feedback_action / record_knowledge_candidate_action / record_validation_action
  三类事实事件如实记录，actor 默认 AI（红线⑥：不伪造人工审批）。
- require_human_actor 守卫：USER 通过，AI / None 抛 EnterpriseRedLineViolationError（红线⑥）。
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
    require_human_actor,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_new_categories_exist() -> None:
    for name, v in (
        ("FEEDBACK", "feedback"),
        ("KNOWLEDGE_CANDIDATE", "knowledge_candidate"),
        ("VALIDATION", "validation"),
    ):
        assert hasattr(AuditActionCategory, name)
        assert getattr(AuditActionCategory, name).value == v


def test_record_feedback_action_default_ai() -> None:
    audit = AuditService(org_id="org-1")
    rec = audit.record_feedback_action(record_id="r1", actor_id="ai", target="f1", detail="d")
    assert rec.category == AuditActionCategory.FEEDBACK
    assert rec.actor_kind == AuditActorKind.AI  # AI 提交记 AI（红线⑥）


def test_record_candidate_and_validation_default_ai() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_candidate_action(record_id="r2", actor_id="ai", target="c1")
    audit.record_validation_action(record_id="r3", actor_id="ai", target="I-1")
    cats = {r.category for r in audit.query()}
    assert AuditActionCategory.KNOWLEDGE_CANDIDATE in cats
    assert AuditActionCategory.VALIDATION in cats
    for r in audit.query():
        assert r.actor_kind == AuditActorKind.AI


def test_user_actor_can_be_explicit() -> None:
    audit = AuditService(org_id="org-1")
    rec = audit.record_feedback_action(
        record_id="r1", actor_id="u-1", actor_kind=AuditActorKind.USER
    )
    assert rec.actor_kind == AuditActorKind.USER  # 人工审核节点亦可如实标注 USER


def test_query_by_category() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_feedback_action(record_id="r1", actor_id="ai", target="f1")
    audit.record_validation_action(record_id="r2", actor_id="ai", target="I-1")
    only_feedback = audit.query(category=AuditActionCategory.FEEDBACK)
    assert len(only_feedback) == 1
    assert only_feedback[0].target == "f1"


def test_require_human_actor_guard() -> None:
    # USER 通过
    require_human_actor(AuditActorKind.USER)
    require_human_actor("user")
    # AI / None 抛红线⑥
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor(AuditActorKind.AI)
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor("ai")
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor(None)


def test_no_record_human_approval() -> None:
    # 红线⑥核心拦截点：审计服务不得把动作记录为人工审批。
    audit = AuditService(org_id="org-1")
    assert not hasattr(type(audit), "record_human_approval")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = audit.record_human_approval


def test_write_fail_closed(monkeypatch) -> None:
    # 构造路径在启用态下即 fail-closed（红线①/⑤）。
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = AuditService(org_id="org-1")
