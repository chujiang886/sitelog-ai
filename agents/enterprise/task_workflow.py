"""Enterprise Operation Layer —— 任务工作流（任务4，Phase 3.8.2）。

新增：``TaskWorkflow``，状态机 ``created -> assigned -> processing -> waiting_review ->
completed``。

红线加固（fail-closed）：
- 人工审核节点**必须 human 驱动**：``record_review_result(reviewer_id, approved)`` 必须
  传入真实 ``reviewer_id``（human）；系统**不提供** ``approve`` 方法（继承
  ``_RedLineForbiddenMixin``，``approve`` / ``engineering_approved`` / ``sign`` /
  ``authorize`` 在结构上不可达，红线②/④）。
- 系统绝不自动审批 / 自动代责（红线⑥）：审核结果只如实登记，是否通过由真实人工决定。
- 所有工作流按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``TaskWorkflowService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 可选联动 ``AuditService`` 如实标注动作发起方（actor 真实）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class TaskWorkflowStatus(str, Enum):
    """任务工作流状态（状态机）。"""

    CREATED = "created"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"


# 状态机允许的（from -> to）跃迁。审核节点（WAITING_REVIEW）只能由人工审核结果驱动。
_ALLOWED_TRANSITIONS: dict[TaskWorkflowStatus, tuple[TaskWorkflowStatus, ...]] = {
    TaskWorkflowStatus.CREATED: (TaskWorkflowStatus.ASSIGNED,),
    TaskWorkflowStatus.ASSIGNED: (TaskWorkflowStatus.PROCESSING,),
    TaskWorkflowStatus.PROCESSING: (TaskWorkflowStatus.WAITING_REVIEW,),
    TaskWorkflowStatus.WAITING_REVIEW: (
        TaskWorkflowStatus.COMPLETED,      # 人工审核通过
        TaskWorkflowStatus.PROCESSING,     # 人工审核打回，重新处理
    ),
    TaskWorkflowStatus.COMPLETED: (),       # 终态
}


@dataclass
class TaskWorkflow:
    """任务工作流（任务4）。

    记录工作流归属（org_id / task_id）、当前状态、审核人（human）与审核结论。
    """

    workflow_id: str
    org_id: str
    task_id: str
    status: TaskWorkflowStatus = TaskWorkflowStatus.CREATED
    reviewer_id: str = ""          # 仅人工审核节点填写（human 驱动）
    review_result: str = ""        # "approved" / "rejected" / ""
    review_note: str = ""
    created_at: str = ""
    updated_at: str = ""


class TaskWorkflowService(_RedLineForbiddenMixin):
    """任务工作流服务（任务4）。

    驱动状态机；审核节点强制 human 驱动；不提供 approve 方法（结构上被 mixin 拦截）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_approve",            # 红线⑥：禁止自动通过
        "auto_sign_off",           # 红线⑥：禁止自动签核
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 TaskWorkflowService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._workflows: dict[str, TaskWorkflow] = {}

    def create_workflow(
        self,
        *,
        workflow_id: str,
        task_id: str,
        created_at: str = "",
    ) -> TaskWorkflow:
        """创建任务工作流（初始状态 CREATED）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建工作流（红线①/⑤）"
            )
        wf = TaskWorkflow(
            workflow_id=workflow_id,
            org_id=self._org_id,
            task_id=task_id,
            status=TaskWorkflowStatus.CREATED,
            created_at=created_at,
            updated_at=created_at,
        )
        self._workflows[workflow_id] = wf
        self._audit_workflow_event(
            workflow_id=workflow_id, actor_id="system", action="workflow_created",
            detail=f"task={task_id}", ts=created_at,
        )
        return wf

    def assign(self, *, workflow_id: str, assignee_id: str) -> TaskWorkflow:
        """分配负责人：CREATED -> ASSIGNED。"""
        return self._transition(
            workflow_id=workflow_id, to=TaskWorkflowStatus.ASSIGNED,
            actor_id=assignee_id, action="workflow_assigned",
            detail=f"assignee={assignee_id}",
        )

    def start_processing(self, *, workflow_id: str) -> TaskWorkflow:
        """开始处理：ASSIGNED -> PROCESSING。"""
        return self._transition(
            workflow_id=workflow_id, to=TaskWorkflowStatus.PROCESSING,
            actor_id="assignee", action="workflow_processing",
        )

    def submit_for_review(self, *, workflow_id: str, submitted_by: str = "") -> TaskWorkflow:
        """提交审核：PROCESSING -> WAITING_REVIEW。

        仅进入等待人工审核状态；**不**代表通过，是否通过须由真实人工在
        ``record_review_result`` 中决定（红线⑥）。
        """
        return self._transition(
            workflow_id=workflow_id, to=TaskWorkflowStatus.WAITING_REVIEW,
            actor_id=submitted_by or "assignee", action="workflow_submitted_for_review",
        )

    def record_review_result(
        self,
        *,
        workflow_id: str,
        reviewer_id: str,
        approved: bool,
        review_note: str = "",
        ts: str = "",
    ) -> TaskWorkflow:
        """记录人工审核结果（**必须 human 驱动**）：WAITING_REVIEW -> COMPLETED / PROCESSING。

        - ``reviewer_id`` 必须非空（真实人工审核人；红线⑥：禁止匿名/系统代审）。
        - ``approved=True`` -> COMPLETED；``approved=False`` -> PROCESSING（打回重做）。
        - 本方法不叫 ``approve``，系统**不提供**任何 approve 入口。
        - 审核结论如实登记，actor_kind=USER（真实人工）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录审核结果（红线①/⑤）"
            )
        wf = self._get_scoped(workflow_id)
        if not reviewer_id:
            raise EnterpriseRedLineViolationError(
                "record_review_result 必须传入真实 reviewer_id（human 驱动），"
                "禁止匿名/系统代审（红线⑥）"
            )
        if wf.status != TaskWorkflowStatus.WAITING_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"工作流 {workflow_id!r} 当前状态 {wf.status.value}，"
                f"仅 WAITING_REVIEW 可记录审核结果"
            )
        to = TaskWorkflowStatus.COMPLETED if approved else TaskWorkflowStatus.PROCESSING
        wf.status = to
        wf.reviewer_id = reviewer_id
        wf.review_result = "approved" if approved else "rejected"
        wf.review_note = review_note
        wf.updated_at = ts
        # 审核结论由真实人工做出，actor_kind 恒为 USER（红线⑥：actor 真实）。
        if self._audit is not None:
            self._audit.record_task_action(
                record_id=f"wf-review-{workflow_id}",
                actor_id=reviewer_id,
                actor_kind=AuditActorKind.USER,
                action="record_review_result",
                target=workflow_id,
                detail=f"result={'approved' if approved else 'rejected'};note={review_note}",
                ts=ts,
            )
        return wf

    def get(self, *, workflow_id: str) -> TaskWorkflow:
        """按组织作用域读取工作流（跨域访问抛隔离错误）。"""
        return self._get_scoped(workflow_id)

    def list_workflows(self, *, task_id: str = "") -> list[TaskWorkflow]:
        """列出当前组织下工作流（可按 task 过滤）。"""
        out = [w for w in self._workflows.values() if w.org_id == self._org_id]
        if task_id:
            out = [w for w in out if w.task_id == task_id]
        return out

    # ---- 内部 ----

    def _transition(
        self,
        *,
        workflow_id: str,
        to: TaskWorkflowStatus,
        actor_id: str,
        action: str,
        detail: str = "",
        ts: str = "",
    ) -> TaskWorkflow:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下驱动工作流（红线①/⑤）"
            )
        wf = self._get_scoped(workflow_id)
        allowed = _ALLOWED_TRANSITIONS.get(wf.status, ())
        if to not in allowed:
            raise EnterpriseRedLineViolationError(
                f"工作流 {workflow_id!r} 非法状态跃迁：{wf.status.value} -> {to.value}"
            )
        wf.status = to
        wf.updated_at = ts
        self._audit_workflow_event(
            workflow_id=workflow_id, actor_id=actor_id, action=action, detail=detail, ts=ts,
        )
        return wf

    def _audit_workflow_event(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        action: str,
        detail: str = "",
        ts: str = "",
    ) -> None:
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"wf-{action}-{workflow_id}",
                actor_id=actor_id,
                action=action,
                target=workflow_id,
                detail=detail,
                ts=ts,
            )

    def _get_scoped(self, workflow_id: str) -> TaskWorkflow:
        from agents.enterprise.organization import EnterpriseIsolationError

        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise EnterpriseIsolationError(f"工作流 {workflow_id!r} 不存在")
        if wf.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"工作流 {workflow_id!r} 归属组织 {wf.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return wf


__all__ = ["TaskWorkflowStatus", "TaskWorkflow", "TaskWorkflowService"]
