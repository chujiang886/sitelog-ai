"""Enterprise Operation Layer —— 测试：协作层红线（fail-closed，Phase 3.8.2）。

覆盖：
- safety_invariants_ok()：当前 config engineering_enabled=false → True。
- Phase 3.8.2 新增服务（TaskService / CommentService / NotificationService /
  TaskWorkflowService）与聚合门面在「启用态」（伪造 engineering_enabled=True）下构造
  一律抛 EnterpriseRedLineViolationError（红线①/⑤）。
- 聚合门面 EnterpriseOperationLayer 装配新子服务（tasks/comments/notifications/workflow）。
- 红线⑥：通知中心伪造人工审批方法名（notify_human_approval / forge_approval）被拦截；
  工作流 approve / sign / authorize 被拦截。
注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.comment import CommentService
from agents.enterprise.notification import NotificationService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.task import TaskService
from agents.enterprise.task_workflow import TaskWorkflowService


def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


@pytest.mark.parametrize(
    "svc_factory",
    [
        lambda: TaskService(org_id="org-1"),
        lambda: CommentService(org_id="org-1"),
        lambda: NotificationService(org_id="org-1"),
        lambda: TaskWorkflowService(org_id="org-1"),
        lambda: EnterpriseOperationLayer(org_id="org-1"),
    ],
)
def test_collab_service_construction_fail_closed(svc_factory, monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_factory()


def test_aggregate_layer_exposes_collab_subservices() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert hasattr(layer, "tasks")
    assert hasattr(layer, "comments")
    assert hasattr(layer, "notifications")
    assert hasattr(layer, "workflow")
    assert layer.is_activation_safe() is True


def test_notification_forge_methods_forbidden_red_line_6() -> None:
    svc = NotificationService(org_id="org-1")
    for name in ("notify_human_approval", "forge_approval"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()  # type: ignore[attr-defined]


def test_workflow_approve_forbidden_red_line_2_4() -> None:
    svc = TaskWorkflowService(org_id="org-1")
    for name in ("approve", "engineering_approved", "sign", "authorize"):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()  # type: ignore[attr-defined]
