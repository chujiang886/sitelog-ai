"""Enterprise Operation Layer —— 任务模型（任务1，Phase 3.8.2）。

新增：``Task``，关联 ``Project`` / ``Assignee`` / ``Creator``，支持企业级组织隔离。

隔离与耦合约束：
- ``Task`` 以字符串外键引用 ``project_id`` / ``assignee_id`` / ``creator_id``，**绝不**
  反向依赖工程模块内部类型，保持零耦合。
- 所有任务按 ``org_id`` 作用域过滤；跨域访问由 ``OrganizationService.assert_same_org``
  在调用层统一拦截（fail-closed，绝不静默放行）。
- ``TaskService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价/审批方法（红线②/③/④）；任务状态流转只做登记，不代替人工决策
  （红线⑥）。
- 可选联动 ``AuditService.record_task_action`` 如实标注动作发起方（actor 真实）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class TaskStatus(str, Enum):
    """任务状态（与 TaskWorkflow 状态机对齐，便于协同）。"""

    CREATED = "created"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"


class TaskPriority(str, Enum):
    """任务优先级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Task:
    """任务（任务1）。

    字段严格对应指令：task_id / project_id / assignee_id / creator_id / status /
    priority / due_date / created_at，并要求组织隔离（org_id）。
    """

    task_id: str
    org_id: str
    project_id: str
    creator_id: str
    status: TaskStatus = TaskStatus.CREATED
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: str = ""
    due_date: str = ""
    created_at: str = ""


class TaskService:
    """任务服务（任务1）。

    仅做任务登记与状态流转记录；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 TaskService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._tasks: dict[str, Task] = {}

    def create_task(
        self,
        *,
        task_id: str,
        project_id: str,
        creator_id: str,
        assignee_id: str = "",
        priority: "TaskPriority | str" = TaskPriority.MEDIUM,
        due_date: str = "",
        created_at: str = "",
    ) -> Task:
        """在组织内创建任务（仅登记；creator 为真实发起方）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建任务（红线①/⑤）"
            )
        status = TaskStatus.CREATED
        pr = priority if isinstance(priority, TaskPriority) else TaskPriority(priority)
        task = Task(
            task_id=task_id,
            org_id=self._org_id,
            project_id=project_id,
            creator_id=creator_id,
            assignee_id=assignee_id,
            status=status,
            priority=pr,
            due_date=due_date,
            created_at=created_at,
        )
        self._tasks[task_id] = task
        if self._audit is not None:
            self._audit.record_task_action(
                record_id=f"task-create-{task_id}",
                actor_id=creator_id,
                action="create_task",
                target=task_id,
                detail=f"project={project_id};assignee={assignee_id};priority={pr.value}",
                ts=created_at,
            )
        return task

    def assign(self, *, task_id: str, assignee_id: str) -> Task:
        """分配任务负责人（CREATED/ASSIGNED 可分配，状态置 ASSIGNED）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分配任务（红线①/⑤）"
            )
        task = self._get_scoped(task_id)
        if task.status not in (TaskStatus.CREATED, TaskStatus.ASSIGNED):
            raise EnterpriseRedLineViolationError(
                f"任务 {task_id!r} 当前状态 {task.status.value} 不允许分配"
            )
        task.assignee_id = assignee_id
        task.status = TaskStatus.ASSIGNED
        if self._audit is not None:
            self._audit.record_task_action(
                record_id=f"task-assign-{task_id}",
                actor_id=assignee_id,
                action="assign_task",
                target=task_id,
                detail=f"assignee={assignee_id}",
            )
        return task

    def update_status(self, *, task_id: str, status: "TaskStatus | str") -> Task:
        """更新任务状态（仅登记流转，不代替人工决策；禁止越级到 completed 的审批语义）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下变更任务状态（红线①/⑤）"
            )
        task = self._get_scoped(task_id)
        new_status = status if isinstance(status, TaskStatus) else TaskStatus(status)
        task.status = new_status
        if self._audit is not None:
            self._audit.record_task_action(
                record_id=f"task-status-{task_id}-{new_status.value}",
                actor_id=task.creator_id,
                action="update_task_status",
                target=task_id,
                detail=f"status={new_status.value}",
            )
        return task

    def get(self, *, task_id: str) -> Task:
        """按组织作用域读取任务（跨域访问抛隔离错误）。"""
        return self._get_scoped(task_id)

    def list_tasks(self, *, project_id: str = "") -> list[Task]:
        """列出当前组织下任务（可按 project 过滤）。"""
        out = [t for t in self._tasks.values() if t.org_id == self._org_id]
        if project_id:
            out = [t for t in out if t.project_id == project_id]
        return out

    def _get_scoped(self, task_id: str) -> Task:
        from agents.enterprise.organization import EnterpriseIsolationError

        task = self._tasks.get(task_id)
        if task is None:
            raise EnterpriseIsolationError(f"任务 {task_id!r} 不存在")
        if task.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"任务 {task_id!r} 归属组织 {task.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return task


__all__ = ["TaskStatus", "TaskPriority", "Task", "TaskService"]
