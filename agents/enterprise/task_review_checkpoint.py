"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 人工复核检查点（任务5，Phase 3.8.12）。

新增：``TaskReviewCheckpoint``。

职责（红线严格限定）：
- 强制复杂任务最终输出 ``requires_human_review=True``；禁止 AI 自动完成最终任务（红线⑥）。
- 提供 ``checkpoint``（校验/强制待复核标志，复杂任务未置位即拒绝自动收口）与
  ``finalize_by_human``（由真实 USER 显式收口，调用 ``require_human_actor``）。
- 不持有 approve（方法名被 mixin 拦截）；绝不自动落地工程结论（红线②/③/④/⑥）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
"""

from __future__ import annotations

from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_task import (
    KnowledgeTask,
    KnowledgeTaskService,
    KnowledgeTaskStatus,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class TaskReviewCheckpoint(_RedLineForbiddenMixin):
    """人工复核检查点（任务5）。

    编排器在收尾时调用 ``checkpoint``：复杂任务未置 ``requires_human_review`` 即拒绝自动收口
    （红线⑥）。唯一「完成」路径是 ``finalize_by_human``，必须由真实 USER 发起。

    本检查点**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/发布/合并/应用知识
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
        "auto_activate",
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
        task_service: "KnowledgeTaskService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "TaskReviewCheckpoint（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._task_service = task_service or KnowledgeTaskService(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )

    def checkpoint(
        self,
        *,
        task: KnowledgeTask,
        is_complex: bool,
        ts: str = "",
    ) -> KnowledgeTask:
        """人工复核闸口（任务5/红线⑥）。

        复杂任务必须 ``requires_human_review=True``，否则拒绝 AI 自动收口（抛
        EnterpriseRedLineViolationError）。简单任务也鼓励置位待复核标志（防御性）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行复核检查点（红线①/⑤）"
            )
        if is_complex and not task.requires_human_review:
            # 红线⑥：复杂任务最终输出必须由人工复核，AI 不得绕过。
            raise EnterpriseRedLineViolationError(
                "红线⑥：复杂任务最终输出 requires_human_review 必须为 True，"
                "AI 不得自动收口（禁止 AI 代替专家/管理责任）"
            )
        if is_complex:
            task.requires_human_review = True
        if self._audit is not None:
            self._audit.record_knowledge_agent_workflow_action(
                record_id=f"cp-{task.task_id}",
                actor_id="checkpoint",
                action="enforce_task_review_checkpoint",
                target=task.task_id,
                detail=(
                    f"requires_human_review={task.requires_human_review};"
                    f"complex={is_complex}"
                ),
                ts=ts,
                actor_kind=AuditActorKind.SYSTEM,
            )
        return task

    def finalize_by_human(
        self,
        *,
        task_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        updated_at: str = "",
        actor_id: str | None = None,
    ) -> KnowledgeTask:
        """由真实 USER 显式收口任务（completed）。AI 不得调用（红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下收口任务（红线①/⑤）"
            )
        # 红线⑥：human-gating，必须由真实人工执行。
        require_human_actor(AuditActorKind.USER)
        return self._task_service.advance_status(
            task_id=task_id,
            status=KnowledgeTaskStatus.COMPLETED,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
            updated_at=updated_at,
            actor_id=actor_id or requesting_user_id,
            actor_kind=AuditActorKind.USER,
        )


__all__ = ["TaskReviewCheckpoint"]
