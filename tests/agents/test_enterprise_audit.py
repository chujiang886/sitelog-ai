"""Enterprise Operation Layer —— 测试5：AI 操作审计（任务5，红线⑥，Phase 3.8.0）。

覆盖：
- record_ai_action / record_user_action / record_workflow_event 如实标注 actor_kind。
- query 按 actor_kind / target 过滤。
- record_human_approval 被拦截（红线⑥）：AI 不得伪造人工审批。
- AuditService 上所有 forbidden 方法名（approve/engineering_approved/quote/
  pricing/sign/authorize）均抛 EnterpriseRedLineViolationError。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditRecord,
    AuditService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_record_ai_action_kind_is_ai() -> None:
    svc = AuditService(org_id="org-1")
    rec = svc.record_ai_action(record_id="r1", actor_id="ai-1", action="draft_solution",
                               target="p1")
    assert rec.actor_kind == AuditActorKind.AI
    assert rec.category == AuditActionCategory.AI_ACTION
    assert rec.org_id == "org-1"


def test_record_user_and_workflow_events() -> None:
    svc = AuditService(org_id="org-1")
    u = svc.record_user_action(record_id="r2", actor_id="u1", action="review")
    w = svc.record_workflow_event(record_id="r3", actor_id="wf", action="completed",
                                  target="p1")
    assert u.actor_kind == AuditActorKind.USER
    assert w.actor_kind == AuditActorKind.SYSTEM
    assert w.category == AuditActionCategory.WORKFLOW_EVENT


def test_query_filters_by_actor_kind_and_target() -> None:
    svc = AuditService(org_id="org-1")
    svc.record_ai_action(record_id="r1", actor_id="ai-1", action="x", target="p1")
    svc.record_user_action(record_id="r2", actor_id="u1", action="y", target="p1")
    svc.record_workflow_event(record_id="r3", actor_id="wf", action="z", target="p2")
    assert len(svc.query(actor_kind=AuditActorKind.AI)) == 1
    assert len(svc.query(target="p1")) == 2
    assert len(svc.query(actor_kind=AuditActorKind.USER, target="p1")) == 1


def test_records_are_plain_data_no_approval_field() -> None:
    svc = AuditService(org_id="org-1")
    rec = svc.record_ai_action(record_id="r1", actor_id="ai-1", action="x")
    assert isinstance(rec, AuditRecord)
    assert "approval" not in rec.action


def test_record_human_approval_is_forbidden_red_line_6() -> None:
    svc = AuditService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_human_approval(actor_id="ai-1", action="approve_solution")  # type: ignore[attr-defined]


def test_forbidden_method_names_raise() -> None:
    svc = AuditService(org_id="org-1")
    for name in ("approve", "engineering_approved", "quote", "pricing", "sign", "authorize"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()
