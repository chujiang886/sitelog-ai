"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 知识任务模型（任务1，Phase 3.8.12）。

新增：
- ``KnowledgeTaskStatus``：任务状态枚举（created / planning / executing / waiting_review /
  completed），状态可追踪。
- ``KnowledgeTask``：一次复杂企业知识任务的实体（task_id / conversation_id / user_id / goal /
  steps / status / created_at），**组织隔离**（org_id 绑定），状态可追踪。
- ``KnowledgeTaskService``：组织作用域内的任务服务（创建 / 读取 / 列举本人任务 / 规划写入 /
  状态推进）。

红线（fail-closed，复用 3.8.0~3.8.11 基座 + 3.8.12 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 任务只承载目标拆解与 Agent 规划的中间态，**绝不自动写知识库、绝不自动生成工程结论**
  （红线③/④：不持有 auto_update_knowledge / auto_merge_knowledge / auto_apply_knowledge /
  generate_engineering_conclusion 等方法）。
- 跨域访问抛 ``EnterpriseIsolationError``；不同用户只能访问自己的任务（任务7 访问隔离）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
- 任务最终态（completed）必须由真实 USER 触发（任务5/红线⑥）；编排器不得自动完成最终任务
  （由 TaskReviewCheckpoint 强制 requires_human_review）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


class KnowledgeTaskStatus(str, Enum):
    """知识任务状态（任务1，状态可追踪）。"""

    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_REVIEW = "waiting_review"
    COMPLETED = "completed"


@dataclass
class KnowledgeTask:
    """知识任务实体（任务1）。

    绑定 ``org_id``（组织隔离）；``user_id`` 标识任务归属人，用于任务7 的访问隔离。
    任务只承载目标拆解与 Agent 规划的中间态；``steps`` 为规划出的步骤描述列表；
    ``requires_human_review`` 由编排器在工作流收尾时强制为 True（任务5）。
    """

    task_id: str
    conversation_id: str
    user_id: str
    goal: str
    org_id: str = ""
    steps: list[str] = field(default_factory=list)
    status: KnowledgeTaskStatus = KnowledgeTaskStatus.CREATED
    requires_human_review: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, KnowledgeTaskStatus):
            self.status = KnowledgeTaskStatus(self.status)


class KnowledgeTaskService(_RedLineForbiddenMixin):
    """知识任务服务（任务1）。

    提供 ``create`` / ``get`` / ``list_for_user`` / ``update_plan`` / ``advance_status``。
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）；跨域/越权访问抛错。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_update_knowledge / auto_merge_knowledge /
    auto_apply_knowledge / generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/发布/合并/应用/学习知识
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
        "auto_activate",
        "auto_learn_user",
        "auto_save_user_to_knowledge",
        "auto_learn",
        "auto_save",
        "publish",
        "merge",
        "apply",
        "commit",
        "write",
        # 红线④/⑤：禁止自动生成工程结论 / 经营决策 / 审批 / 管理建议
        "generate_engineering_conclusion",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeTaskService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._tasks: dict[str, KnowledgeTask] = {}

    def create(
        self,
        *,
        task_id: str,
        conversation_id: str,
        user_id: str,
        goal: str,
        created_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeTask:
        """创建一次知识任务（由用户发起，默认 USER 审计；绝不写知识库，红线③/④）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建任务（红线①/⑤）"
            )
        task = KnowledgeTask(
            task_id=task_id,
            conversation_id=conversation_id,
            user_id=user_id,
            goal=goal,
            org_id=self._org_id,
            status=KnowledgeTaskStatus.CREATED,
            created_at=created_at,
            updated_at=created_at,
        )
        self._tasks[task_id] = task
        if self._audit is not None:
            self._audit.record_knowledge_task_action(
                record_id=f"task-{task_id}",
                actor_id=actor_id or user_id,
                action="create_knowledge_task",
                target=task_id,
                detail=f"goal={goal};user_id={user_id};conversation_id={conversation_id}",
                ts=created_at,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return task

    def _get_scoped(self, task_id: str) -> KnowledgeTask:
        from agents.enterprise.organization import EnterpriseIsolationError

        t = self._tasks.get(task_id)
        if t is None:
            raise EnterpriseIsolationError(f"知识任务 {task_id!r} 不存在")
        if t.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识任务 {task_id!r} 归属组织 {t.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return t

    def _assert_owner_or_admin(
        self, *, task: KnowledgeTask,
        requesting_user_id: str, requesting_role: "RoleKind | None",
    ) -> None:
        if requesting_user_id == task.user_id:
            return
        if requesting_role == RoleKind.ADMIN:
            return
        raise EnterpriseRedLineViolationError(
            f"用户 {requesting_user_id!r} 无权访问任务 {task.task_id!r}："
            f"仅任务归属人或 ADMIN 可访问（红线⑥/任务7 访问隔离）"
        )

    def get(
        self,
        *,
        task_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> KnowledgeTask:
        """按组织作用域 + 访问隔离读取任务（跨域/越权抛错）。"""
        task = self._get_scoped(task_id)
        self._assert_owner_or_admin(
            task=task,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        return task

    def list_for_user(self, *, user_id: str) -> list[KnowledgeTask]:
        """列举某用户的全部任务（组织作用域过滤；仅返回本人任务，满足访问隔离）。"""
        out: list[KnowledgeTask] = []
        for t in self._tasks.values():
            if t.org_id != self._org_id:
                continue
            if t.user_id == user_id:
                out.append(t)
        return out

    def update_plan(
        self,
        *,
        task_id: str,
        steps: "list[str]",
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        updated_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeTask:
        """写入规划步骤（planning 态；只拆解不执行决策，红线③/④）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下规划任务（红线①/⑤）"
            )
        task = self.get(
            task_id=task_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        task.steps = list(steps)
        task.status = KnowledgeTaskStatus.PLANNING
        task.updated_at = updated_at
        if self._audit is not None:
            self._audit.record_knowledge_task_action(
                record_id=f"task-plan-{task_id}",
                actor_id=actor_id or requesting_user_id,
                action="update_task_plan",
                target=task_id,
                detail=f"steps={len(task.steps)};status=planning",
                ts=updated_at,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return task

    def advance_status(
        self,
        *,
        task_id: str,
        status: "KnowledgeTaskStatus | str",
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        updated_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeTask:
        """状态推进（created→planning→executing→waiting_review→completed）。

        进入 ``completed`` 必须由真实 USER 触发（任务5/红线⑥）；编排器不得自动把任务标为
        completed（由 TaskReviewCheckpoint 强制 requires_human_review）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推进任务状态（红线①/⑤）"
            )
        new_status = (
            status if isinstance(status, KnowledgeTaskStatus) else KnowledgeTaskStatus(status)
        )
        if new_status is KnowledgeTaskStatus.COMPLETED:
            # 红线⑥：最终完成必须由真实人工发起。
            require_human_actor(actor_kind or AuditActorKind.USER)
        task = self.get(
            task_id=task_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        task.status = new_status
        task.updated_at = updated_at
        if self._audit is not None:
            self._audit.record_knowledge_task_action(
                record_id=f"task-status-{task_id}",
                actor_id=actor_id or requesting_user_id,
                action="advance_task_status",
                target=task_id,
                detail=f"status={new_status.value}",
                ts=updated_at,
                actor_kind=actor_kind or (
                    AuditActorKind.USER if new_status is KnowledgeTaskStatus.COMPLETED
                    else AuditActorKind.AI
                ),
            )
        return task


__all__ = ["KnowledgeTaskStatus", "KnowledgeTask", "KnowledgeTaskService"]
