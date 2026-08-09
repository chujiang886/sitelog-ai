"""Enterprise Operation Layer —— 测试：任务模型（任务1，Phase 3.8.2）。

覆盖：
- Task 字段（task_id / project_id / assignee_id / creator_id / status / priority /
  due_date / created_at）与组织隔离（org_id）。
- TaskService 创建 / 分配 / 状态流转 / 读取 / 列表。
- 跨域访问抛 EnterpriseIsolationError（组织隔离，fail-closed）。
- 写路径联动审计（record_task_action，actor 真实）。
- TaskService 构造 fail-closed（红线①/⑤）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.task import Task, TaskPriority, TaskService, TaskStatus


def test_create_task_fields_and_org() -> None:
    svc = TaskService(org_id="org-1")
    t = svc.create_task(
        task_id="T1",
        project_id="P1",
        creator_id="u-creator",
        assignee_id="",
        priority="high",
        due_date="2026-08-10",
        created_at="2026-08-02T10:00",
    )
    assert isinstance(t, Task)
    assert t.task_id == "T1"
    assert t.project_id == "P1"
    assert t.creator_id == "u-creator"
    assert t.assignee_id == ""
    assert t.status == TaskStatus.CREATED
    assert t.priority == TaskPriority.HIGH
    assert t.due_date == "2026-08-10"
    assert t.created_at == "2026-08-02T10:00"
    assert t.org_id == "org-1"


def test_assign_and_update_status_flow() -> None:
    svc = TaskService(org_id="org-1")
    svc.create_task(task_id="T1", project_id="P1", creator_id="u-creator")
    a = svc.assign(task_id="T1", assignee_id="u-ops")
    assert a.status == TaskStatus.ASSIGNED
    assert a.assignee_id == "u-ops"
    u = svc.update_status(task_id="T1", status="processing")
    assert u.status == TaskStatus.PROCESSING
    # 列表过滤
    svc.create_task(task_id="T2", project_id="P2", creator_id="u-creator")
    assert len(svc.list_tasks()) == 2
    assert len(svc.list_tasks(project_id="P1")) == 1


def test_cross_org_isolation_raises() -> None:
    svc1 = TaskService(org_id="org-1")
    svc2 = TaskService(org_id="org-2")
    svc2.create_task(task_id="T2", project_id="P2", creator_id="u2")
    # org-1 访问 org-2 的任务 → 隔离错误
    with pytest.raises(EnterpriseIsolationError):
        svc1.get(task_id="T2")


def test_task_audit_linkage_records_real_actor() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = TaskService(org_id="org-1", audit=audit)
    svc.create_task(task_id="T1", project_id="P1", creator_id="u-creator")
    svc.assign(task_id="T1", assignee_id="u-ops")
    collab = audit.query(category=AuditActionCategory.COLLABORATION)
    assert len(collab) == 2
    assert all(r.category == AuditActionCategory.COLLABORATION for r in collab)
    assert collab[0].actor_id == "u-creator"
    assert collab[1].actor_id == "u-ops"
    assert collab[0].actor_kind == AuditActorKind.USER


def test_service_construction_fail_closed(monkeypatch) -> None:
    from agents.enterprise.red_line import safety_invariants_ok

    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        TaskService(org_id="org-1")
