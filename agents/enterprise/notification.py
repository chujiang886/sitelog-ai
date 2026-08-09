"""Enterprise Operation Layer —— 通知中心（任务3，Phase 3.8.2）。

新增：``Notification``，支持「任务变化 / 审核提醒 / 权限变化」三类通知。

红线加固（fail-closed）：
- 通知中心**禁止伪造人工审批通知**：``notify_human_approval`` / ``forge_approval`` 是被
  拦截的 forbidden 方法名（命中即抛 ``EnterpriseRedLineViolationError``，红线⑥）。
- ``NotificationService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 所有通知按 ``org_id`` 作用域过滤；跨域访问由组织隔离层统一拦截（fail-closed）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；通知只如实描述事件，绝不代替人工决策。
- 可选联动 ``AuditService.record_notification_action`` 如实标注动作发起方。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class NotificationKind(str, Enum):
    """通知类型（任务变化 / 审核提醒 / 权限变化）。"""

    TASK_CHANGED = "task_changed"
    REVIEW_REMINDER = "review_reminder"
    PERMISSION_CHANGED = "permission_changed"


@dataclass
class Notification:
    """通知（任务3）。

    记录 recipient / kind / title / body / ts / read，并要求组织隔离（org_id）。
    """

    notification_id: str
    org_id: str
    recipient_id: str
    kind: NotificationKind
    title: str
    body: str
    ts: str = ""
    read: bool = False


class NotificationService(_RedLineForbiddenMixin):
    """通知中心服务（任务3）。

    仅做通知登记与读取；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。

    红线⑥加固：``notify_human_approval`` / ``forge_approval`` 在结构上不可达
    （继承 ``_RedLineForbiddenMixin``，扩展 forbidden 名单）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "notify_human_approval",   # 红线⑥：禁止伪造人工审批通知
        "forge_approval",          # 红线⑥：禁止伪造审批
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 NotificationService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._notifications: dict[str, Notification] = {}

    def push(
        self,
        *,
        notification_id: str,
        recipient_id: str,
        kind: "NotificationKind | str",
        title: str,
        body: str,
        ts: str = "",
    ) -> Notification:
        """在组织内向接收人推送一条通知（仅如实描述事件；不得伪装为人工审批）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推送通知（红线①/⑤）"
            )
        nk = kind if isinstance(kind, NotificationKind) else NotificationKind(kind)
        note = Notification(
            notification_id=notification_id,
            org_id=self._org_id,
            recipient_id=recipient_id,
            kind=nk,
            title=title,
            body=body,
            ts=ts,
            read=False,
        )
        self._notifications[notification_id] = note
        if self._audit is not None:
            self._audit.record_notification_action(
                record_id=f"notify-push-{notification_id}",
                actor_id=recipient_id,
                action="push_notification",
                target=notification_id,
                detail=f"kind={nk.value}",
                ts=ts,
            )
        return note

    def mark_read(self, *, notification_id: str) -> Notification:
        """标记通知为已读（写路径断言红线①/⑤）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下更新通知（红线①/⑤）"
            )
        note = self._get_scoped(notification_id)
        note.read = True
        if self._audit is not None:
            self._audit.record_notification_action(
                record_id=f"notify-read-{notification_id}",
                actor_id=note.recipient_id,
                action="mark_notification_read",
                target=notification_id,
            )
        return note

    def get(self, *, notification_id: str) -> Notification:
        """按组织作用域读取通知（跨域访问抛隔离错误）。"""
        return self._get_scoped(notification_id)

    def list_for(self, *, recipient_id: str) -> list[Notification]:
        """列出某接收人在当前组织下的全部通知。"""
        return [
            n
            for n in self._notifications.values()
            if n.org_id == self._org_id and n.recipient_id == recipient_id
        ]

    def _get_scoped(self, notification_id: str) -> Notification:
        from agents.enterprise.organization import EnterpriseIsolationError

        note = self._notifications.get(notification_id)
        if note is None:
            raise EnterpriseIsolationError(f"通知 {notification_id!r} 不存在")
        if note.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"通知 {notification_id!r} 归属组织 {note.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return note


__all__ = ["NotificationKind", "Notification", "NotificationService"]
