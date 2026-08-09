"""Enterprise Operation Layer —— 测试：审计增强（任务5，Phase 3.8.2）。

覆盖：
- AuditActionCategory.COLLABORATION 新增。
- record_task_action / record_comment_action / record_notification_action 如实记录，
  category=COLLABORATION，actor_kind 默认 USER，可显式指定 AI/SYSTEM。
- 保持红线⑥：record_human_approval 仍被拦截（AuditService 上 forbidden 方法名）。
- query 按 category=COLLABORATION 过滤。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_collaboration_category_exists() -> None:
    assert AuditActionCategory.COLLABORATION == AuditActionCategory("collaboration")


def test_record_task_action_default_user() -> None:
    svc = AuditService(org_id="org-1")
    rec = svc.record_task_action(record_id="r1", actor_id="u1", action="create_task",
                                 target="T1", detail="x")
    assert rec.category == AuditActionCategory.COLLABORATION
    assert rec.actor_kind == AuditActorKind.USER
    assert rec.action == "create_task"


def test_record_comment_and_notification_action() -> None:
    svc = AuditService(org_id="org-1")
    c = svc.record_comment_action(record_id="r2", actor_id="u2", action="add_comment",
                                  target="T1")
    n = svc.record_notification_action(record_id="r3", actor_id="u3", action="push_notification",
                                       target="N1")
    assert c.category == AuditActionCategory.COLLABORATION
    assert n.category == AuditActionCategory.COLLABORATION
    assert c.actor_kind == AuditActorKind.USER
    assert n.actor_kind == AuditActorKind.USER


def test_actor_kind_override_preserved() -> None:
    svc = AuditService(org_id="org-1")
    rec = svc.record_task_action(record_id="r4", actor_id="ai-1", action="auto_suggest",
                                 actor_kind=AuditActorKind.AI)
    assert rec.actor_kind == AuditActorKind.AI
    rec2 = svc.record_notification_action(record_id="r5", actor_id="sys", action="system_notify",
                                          actor_kind=AuditActorKind.SYSTEM)
    assert rec2.actor_kind == AuditActorKind.SYSTEM


def test_query_by_collaboration_category() -> None:
    svc = AuditService(org_id="org-1")
    svc.record_task_action(record_id="r1", actor_id="u1", action="create_task")
    svc.record_ai_action(record_id="r2", actor_id="ai-1", action="draft")
    svc.record_comment_action(record_id="r3", actor_id="u2", action="add_comment")
    collab = svc.query(category=AuditActionCategory.COLLABORATION)
    assert len(collab) == 2
    assert all(r.category == AuditActionCategory.COLLABORATION for r in collab)


def test_record_human_approval_still_forbidden_red_line_6() -> None:
    svc = AuditService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_human_approval(actor_id="ai-1", action="approve_solution")  # type: ignore[attr-defined]
