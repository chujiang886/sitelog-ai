"""Enterprise Operation Layer —— 测试：通知中心（任务3，Phase 3.8.2）。

覆盖：
- Notification 三类（TASK_CHANGED / REVIEW_REMINDER / PERMISSION_CHANGED）与字段。
- NotificationService 推送 / 已读 / 读取 / 列表（按接收人）。
- 跨域访问抛 EnterpriseIsolationError（组织隔离，fail-closed）。
- 写路径联动审计（record_notification_action，actor 真实）。
- 红线⑥：``notify_human_approval`` / ``forge_approval`` 被拦截（禁止伪造人工审批通知）。
- NotificationService 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.notification import (
    Notification,
    NotificationKind,
    NotificationService,
)
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_push_three_kinds_and_read() -> None:
    svc = NotificationService(org_id="org-1")
    n1 = svc.push(notification_id="N1", recipient_id="u1", kind="task_changed",
                  title="任务变更", body="T1 已分配", ts="t1")
    n2 = svc.push(notification_id="N2", recipient_id="u1", kind="review_reminder",
                  title="审核提醒", body="R1 待审核", ts="t2")
    n3 = svc.push(notification_id="N3", recipient_id="u2", kind="permission_changed",
                  title="权限变更", body="角色已更新", ts="t3")
    assert n1.kind == NotificationKind.TASK_CHANGED
    assert n2.kind == NotificationKind.REVIEW_REMINDER
    assert n3.kind == NotificationKind.PERMISSION_CHANGED
    assert all(isinstance(n, Notification) for n in (n1, n2, n3))
    assert n1.read is False
    svc.mark_read(notification_id="N1")
    assert svc.get(notification_id="N1").read is True
    # 按接收人过滤
    assert len(svc.list_for(recipient_id="u1")) == 2
    assert len(svc.list_for(recipient_id="u2")) == 1


def test_cross_org_isolation_raises() -> None:
    svc1 = NotificationService(org_id="org-1")
    svc2 = NotificationService(org_id="org-2")
    svc2.push(notification_id="N2", recipient_id="u2", kind="task_changed",
              title="x", body="y")
    with pytest.raises(EnterpriseIsolationError):
        svc1.get(notification_id="N2")


def test_notification_audit_linkage_records_real_actor() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = NotificationService(org_id="org-1", audit=audit)
    svc.push(notification_id="N1", recipient_id="u1", kind="task_changed",
             title="x", body="y", ts="t1")
    svc.mark_read(notification_id="N1")
    collab = audit.query(category=AuditActionCategory.COLLABORATION)
    assert len(collab) == 2
    assert {r.action for r in collab} == {"push_notification", "mark_notification_read"}
    assert all(r.actor_kind == AuditActorKind.USER for r in collab)


def test_forge_human_approval_notification_is_forbidden_red_line_6() -> None:
    svc = NotificationService(org_id="org-1")
    for name in ("notify_human_approval", "forge_approval"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()  # type: ignore[attr-defined]


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        NotificationService(org_id="org-1")
