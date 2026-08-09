"""Phase 3.8.25 企业智能体治理工作流编排器（编排层核心）。

定位：**复用而非重建**。本编排器把「用户问题 → 事实辅助分析（3.8.24 助手）→
人工研判 → 治理任务创建（3.8.21 问责层）→ 执行跟踪 → 结果归档 → 审计闭环」串成
一条可追踪流水线，自己**不重写** 3.8.21 问责层、3.8.24 知识助手、既有权限/身份/
可见性策略，只**组合调用**它们。

与本仓库既有企业层服务一致，本类继承 ``_RedLineForbiddenMixin``，并通过
``_FORBIDDEN = _WORKFLOW_FORBIDDEN``（结构级禁名）拦截自动审批 / 自动执行 / 自动
关闭 / 自动生成策略 / 代替责任人等禁名方法。

红线（fail-closed，六条，与主理人 Phase 3.8.25 指令一致）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② 不输出 ``engineering_approved``（继承自 3.8.21，已在 ``_FORBIDDEN`` 内）。
③ 禁 AI 自动治理 / 自动审批 / 自动关闭问题：所有前进状态转移的人工节点均
   ``require_human_actor(USER)``；AI 仅能 ``register_candidate``（落 CREATED 候选）
   与 ``submit_for_review``（推入人工研判队列，不构成治理决定）。
④ 禁 AI 自动执行治理动作：``submit_execution_result`` 强制
   ``require_human_actor(USER)`` 且 ``GovernanceExecutionRecord.actor_kind`` 必须为
   ``user``。
⑤ 禁 AI 自动生成治理策略 / 改知识：所有文本经六组语义扫描（``_reject_all_markers``）。
⑥ 禁 AI 代替治理责任人：人工确认 / 执行 / 完成 / 归档 / 备注全部
   ``require_human_actor(USER)``，审计留痕 actor / time / decision / reason。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.agent_governance_workflow import (
    GovernanceTaskSourceType,
)
from agents.enterprise.audit import AuditActorKind
from agents.enterprise.governance_workflow.forbidden import _WORKFLOW_FORBIDDEN
from agents.enterprise.governance_workflow.models import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
    _reject_all_markers,
)
from agents.enterprise.identity import IdentityService
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class GovernanceWorkflowOrchestrator(_RedLineForbiddenMixin):
    """治理工作流编排器（任务1/2/3/4/5 主体）。

    说明：3.8.25 的六态机 ``CREATED → UNDER_REVIEW → HUMAN_CONFIRMED →
    IN_PROGRESS → WAITING_RESULT → COMPLETED`` 由本类驱动；3.8.21 的
    ``GovernanceWorkflowService``（五态问责机）作为**可选**依赖在
    ``human_confirm`` 通过时派生「治理任务」，二者并存、互不覆盖。
    """

    # 结构级红线拦截：编排层禁名（继承 3.8.21 + 编排专属增量）。
    _FORBIDDEN = _WORKFLOW_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: Any = None,
        identity: "Optional[IdentityService]" = None,
        visibility: "Optional[KnowledgeVisibilityPolicy]" = None,
        permission_policy: "Optional[AgentPermissionPolicy]" = None,
        governance_workflow: Any = None,  # 3.8.21 问责层服务（可选）
        assistant: Any = None,            # 3.8.24 知识助手（可选）
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceWorkflowOrchestrator（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._governance_workflow = governance_workflow
        self._assistant = assistant

        # 内存存储（与全仓库既有企业层一致，无 ORM）。
        self._workflows: Dict[str, GovernanceWorkflow] = {}
        self._reviews: Dict[str, GovernanceWorkflowReview] = {}
        self._executions: Dict[str, List[GovernanceExecutionRecord]] = {}
        self._archived: Dict[str, GovernanceWorkflow] = {}

    # ------------------------------------------------------------------
    # 隔离与访问控制（红线⑤/⑥：默认拒绝 + 组织隔离）
    # ------------------------------------------------------------------

    def _ensure_org_scope(self, target_org: str, op: str) -> None:
        """跨组织访问拦截（补 3.8.21 问责层之缺）。

        请求 org 与服务 org 不一致即抛 ``EnterpriseIsolationError``，绝不静默放行。
        """
        tgt = str(target_org or "").strip()
        if self._org_id and tgt and tgt != self._org_id:
            raise EnterpriseIsolationError(
                f"{op} 拒绝跨组织访问：服务 org={self._org_id!r} 但请求 org={tgt!r}"
                f"（红线⑤/⑥：禁止跨组织读取/处置治理工作流）"
            )

    def _ensure_access(
        self, *, user: Any = None, resource_category: str = "governance_workflow"
    ) -> None:
        """默认拒绝的权限闸门（复用 AgentPermissionPolicy）。

        无权限策略或未传 user 时，仅组织隔离生效；有权限策略且判定拒绝时抛红线违例。
        """
        if self._permission_policy is not None and user is not None:
            allowed = False
            try:
                allowed = bool(
                    self._permission_policy.check_agent_access(
                        user=user, resource_category=resource_category
                    )
                )
            except Exception:
                allowed = False
            if not allowed:
                raise EnterpriseRedLineViolationError(
                    f"权限策略拒绝访问 resource_category={resource_category!r}（默认拒绝，红线⑤）"
                )

    def _get_workflow(self, workflow_id: str) -> GovernanceWorkflow:
        wf = self._workflows.get(str(workflow_id).strip())
        if wf is None:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 不存在：禁止凭空处置治理工作流（红线⑥：可溯源）"
            )
        return wf

    # ------------------------------------------------------------------
    # 任务1/2：候选登记 + 连接知识助手
    # ------------------------------------------------------------------

    def register_candidate(
        self,
        *,
        workflow_id: str,
        source_type: "GovernanceWorkflowSourceType | str",
        source_id: str,
        title: str = "",
        description: str = "",
        source_facts: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        created_at: str = "",
        actor_id: str = "ai",
        draft_id: str = "",
        task_id: str = "",
    ) -> GovernanceWorkflow:
        """登记一条治理工作流**候选**（AI 可发起，红线③）。

        仅落 ``CREATED`` 候选态；不自动派发、不自动研判、不自动关闭。
        """
        self._ensure_org_scope(self._org_id, "register_candidate")
        wf = GovernanceWorkflow(
            workflow_id=workflow_id,
            source_type=source_type,
            source_id=source_id,
            org_id=self._org_id,
            title=title,
            description=description,
            source_facts=source_facts or [],
            references=references or [],
            created_at=created_at,
            created_by=actor_id,
            draft_id=draft_id,
            task_id=task_id,
        )
        self._workflows[wf.workflow_id] = wf
        if self._audit is not None:
            self._audit.record_agent_governance_workflow_create_action(
                record_id=f"gw-create-{wf.workflow_id}",
                actor_id=actor_id,
                target=wf.workflow_id,
                detail=wf.summary(),
                ts=created_at,
                actor_kind=AuditActorKind.AI,
            )
        return wf

    def create_from_answer_draft(
        self,
        *,
        draft: Any,
        workflow_id: Optional[str] = None,
        title: str = "",
        description: str = "",
        created_at: str = "",
        actor_id: str = "ai",
    ) -> GovernanceWorkflow:
        """从 3.8.24 知识助手答案草稿创建工作流候选（Task2，红线③/⑥）。

        草稿必须 ``requires_human_review is True`` 且来源为真实人工/AI 事实草稿；
        本方法**绝不**调用 3.8.21 任何治理动作，仅登记候选并写审计。
        """
        req_review = getattr(draft, "requires_human_review", None)
        if req_review is not True:
            raise EnterpriseRedLineViolationError(
                "GovernanceAnswerDraft.requires_human_review 必须为 True："
                "禁止把未经验证的助手答案转为治理工作流（红线③/⑥）"
            )
        answer_id = str(getattr(draft, "answer_id", "") or "").strip()
        if not answer_id:
            raise EnterpriseRedLineViolationError(
                "草稿缺少 answer_id：治理工作流必须可溯源到一条真实助手答案（红线⑥）"
            )
        wid = workflow_id or f"gw-{answer_id}"
        return self.register_candidate(
            workflow_id=wid,
            source_type=GovernanceWorkflowSourceType.ASSISTANT_DRAFT,
            source_id=answer_id,
            title=title or f"治理线索（源自助手答案 {answer_id}）",
            description=description or str(getattr(draft, "summary", "") or ""),
            source_facts=list(getattr(draft, "facts", []) or []),
            references=list(getattr(draft, "references", []) or []),
            created_at=created_at,
            actor_id=actor_id,
            draft_id=answer_id,
        )

    # ------------------------------------------------------------------
    # 状态机驱动（复用 models.py 的合法迁移表；非法迁移直接拒绝）
    # ------------------------------------------------------------------

    def submit_for_review(
        self,
        *,
        workflow_id: str,
        actor_id: str = "ai",
        actor_kind: Any = None,
        timestamp: str = "",
    ) -> GovernanceWorkflow:
        """推入人工研判队列（CREATED → UNDER_REVIEW，红线③）。

        AI 可推送（不构成治理决定）；记录推送事实。组织隔离前置校验。
        """
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "submit_for_review")
        if not wf.can_transition_to(GovernanceWorkflowStatus.UNDER_REVIEW):
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 非法状态迁移："
                f"{wf.status.value} → under_review（红线③/⑥）"
            )
        wf.status = GovernanceWorkflowStatus.UNDER_REVIEW
        if self._audit is not None:
            self._audit.record_agent_governance_workflow_review_action(
                record_id=f"gw-review-{workflow_id}",
                actor_id=actor_id,
                action="submit_workflow_for_review",
                target=workflow_id,
                detail=wf.summary(),
                ts=timestamp,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return wf

    def human_confirm(
        self,
        *,
        workflow_id: str,
        reviewer_id: str,
        reviewer_kind: Any,
        decision: "WorkflowReviewDecision | str",
        reason: str,
        reviewed_at: str = "",
        org_id: Optional[str] = None,
        derive_task: bool = False,
        task_id: Optional[str] = None,
    ) -> GovernanceWorkflowReview:
        """人工研判确认（UNDER_REVIEW → HUMAN_CONFIRMED，红线③/⑥）。

        强制 ``require_human_actor(USER)``；仅 CONFIRMED 才推进状态。可选在确认通过时
        派生一条 3.8.21 治理任务（仍由真实人工作为 actor，红线④不越权）。
        """
        # 红线⑥核心：确认人必须是真实 USER。
        from agents.enterprise.audit import require_human_actor

        require_human_actor(reviewer_kind)
        scope_org = org_id or self._org_id
        self._ensure_org_scope(scope_org, "human_confirm")

        wf = self._get_workflow(workflow_id)
        if wf.status is not GovernanceWorkflowStatus.UNDER_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 当前 {wf.status.value}，"
                f"human_confirm 仅允许在 under_review 态（红线③/⑥）"
            )

        decision_enum = WorkflowReviewDecision(decision)
        review = GovernanceWorkflowReview(
            review_id=f"gwr-{workflow_id}-{reviewed_at or 'now'}",
            workflow_id=workflow_id,
            reviewer_id=reviewer_id,
            reviewer_kind=reviewer_kind,
            decision=decision_enum,
            reason=reason,
            reviewed_at=reviewed_at,
            org_id=scope_org,
        )
        self._reviews[review.review_id] = review

        if self._audit is not None:
            self._audit.record_agent_governance_workflow_review_action(
                record_id=review.review_id,
                actor_id=reviewer_id,
                action="human_confirm_governance_workflow",
                target=workflow_id,
                detail=f"decision={decision_enum.value} reason={reason}",
                ts=reviewed_at,
                actor_kind=AuditActorKind.USER,
            )

        if decision_enum is WorkflowReviewDecision.CONFIRMED:
            wf.status = GovernanceWorkflowStatus.HUMAN_CONFIRMED
            wf.confirmed_by = reviewer_id
            wf.confirmed_at = reviewed_at
            if derive_task and self._governance_workflow is not None:
                tid = task_id or f"gt-{workflow_id}"
                self._governance_workflow.create_task(
                    task_id=tid,
                    source_type=GovernanceTaskSourceType.GOVERNANCE_INSIGHT,
                    source_id=workflow_id,
                    title=wf.title,
                    detail=wf.description,
                    created_at=reviewed_at,
                    actor_id=reviewer_id,
                    actor_kind=AuditActorKind.USER,
                )
                wf.task_id = tid
        return review

    # ------------------------------------------------------------------
    # 任务4/5：执行跟踪 + 任务追踪（全部人工节点）
    # ------------------------------------------------------------------

    def start_execution(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
        note: str = "",
    ) -> GovernanceWorkflow:
        """真实人工开始执行治理动作（HUMAN_CONFIRMED → IN_PROGRESS，红线④）。"""
        from agents.enterprise.audit import require_human_actor

        require_human_actor(actor_kind)
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "start_execution")
        if not wf.can_transition_to(GovernanceWorkflowStatus.IN_PROGRESS):
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 非法状态迁移："
                f"{wf.status.value} → in_progress（红线④/⑥）"
            )
        wf.status = GovernanceWorkflowStatus.IN_PROGRESS
        self._record_execution_audit(
            workflow_id=workflow_id, actor_id=actor_id,
            action="human_start_execution", detail=note or wf.summary(),
            ts=timestamp,
        )
        return wf

    def submit_execution_result(
        self,
        *,
        workflow_id: str,
        action: str,
        actor: str,
        actor_kind: Any = "user",
        timestamp: str = "",
        result: str = "",
        source: str = "",
        note: str = "",
        record_id: Optional[str] = None,
    ) -> GovernanceExecutionRecord:
        """提交真实人工执行结果（IN_PROGRESS → WAITING_RESULT，红线④/⑥）。

        强制 ``require_human_actor(USER)``；``GovernanceExecutionRecord`` 构造期即强制
        ``actor_kind == 'user'``（非人类执行者标识构造即拒）。
        """
        from agents.enterprise.audit import require_human_actor

        require_human_actor(actor_kind)
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "submit_execution_result")

        # GovernanceExecutionRecord 的 actor_kind 期望字面字符串 "user"（其 __post_init__
        # 会做 str().lower()，枚举会被转成 "auditactorkind.user" 而拒绝）。红线闸门
        # require_human_actor(actor_kind) 已校验为真实 USER，此处固化为规范字面量。
        rec = GovernanceExecutionRecord(
            record_id=record_id or f"ger-{workflow_id}-{timestamp or 'now'}",
            workflow_id=workflow_id,
            action=action,
            actor=actor,
            actor_kind="user",
            timestamp=timestamp,
            result=result,
            source=source or f"workflow:{workflow_id}",
            note=note,
            org_id=self._org_id,
        )
        self._executions.setdefault(workflow_id, []).append(rec)

        if not wf.can_transition_to(GovernanceWorkflowStatus.WAITING_RESULT):
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 非法状态迁移："
                f"{wf.status.value} → waiting_result（红线④/⑥）"
            )
        wf.status = GovernanceWorkflowStatus.WAITING_RESULT
        self._record_execution_audit(
            workflow_id=workflow_id, actor_id=actor,
            action="human_track_governance_execution", detail=result or rec.summary(),
            ts=timestamp,
        )
        return rec

    def human_complete(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
        note: str = "",
    ) -> GovernanceWorkflow:
        """真实人工确认完成（WAITING_RESULT → COMPLETED，红线③/⑥）。"""
        from agents.enterprise.audit import require_human_actor

        require_human_actor(actor_kind)
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "human_complete")
        if wf.status is not GovernanceWorkflowStatus.WAITING_RESULT:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 当前 {wf.status.value}，"
                f"human_complete 仅允许在 waiting_result 态（红线③/⑥）"
            )
        wf.status = GovernanceWorkflowStatus.COMPLETED
        wf.completed_by = actor_id
        wf.completed_at = timestamp
        self._record_execution_audit(
            workflow_id=workflow_id, actor_id=actor_id,
            action="human_complete_workflow", detail=note or wf.summary(),
            ts=timestamp,
        )
        return wf

    def append_note(
        self,
        *,
        workflow_id: str,
        note: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
    ) -> GovernanceWorkflow:
        """追加真实人工备注（红线③/④/⑤/⑥：语义扫描 + 人工闸门）。"""
        from agents.enterprise.audit import require_human_actor

        require_human_actor(actor_kind)
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "append_note")
        _reject_all_markers(
            note, ctx=f"GovernanceWorkflow {workflow_id!r} 的 human_notes"
        )
        wf.human_notes.append(str(note).strip())
        self._record_execution_audit(
            workflow_id=workflow_id, actor_id=actor_id,
            action="human_append_workflow_note", detail=note, ts=timestamp,
        )
        return wf

    def archive(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
    ) -> GovernanceWorkflow:
        """真实人工归档（仅 completed 态，红线③/⑥）。"""
        from agents.enterprise.audit import require_human_actor

        require_human_actor(actor_kind)
        wf = self._get_workflow(workflow_id)
        self._ensure_org_scope(wf.org_id or self._org_id, "archive")
        if wf.status is not GovernanceWorkflowStatus.COMPLETED:
            raise EnterpriseRedLineViolationError(
                f"GovernanceWorkflow {workflow_id!r} 仅允许在 completed 态归档（红线③/⑥）"
            )
        wf.archived = True
        wf.archived_by = actor_id
        wf.archived_at = timestamp
        self._archived[workflow_id] = wf
        self._record_execution_audit(
            workflow_id=workflow_id, actor_id=actor_id,
            action="human_archive_workflow", detail=wf.summary(), ts=timestamp,
        )
        return wf

    def _record_execution_audit(
        self, *, workflow_id: str, actor_id: str, action: str, detail: str, ts: str
    ) -> None:
        if self._audit is not None:
            self._audit.record_agent_governance_workflow_execution_action(
                record_id=f"gw-exec-{workflow_id}-{action}",
                actor_id=actor_id,
                action=action,
                target=workflow_id,
                detail=detail,
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )

    # ------------------------------------------------------------------
    # 只读查询（默认拒绝 + 组织隔离）
    # ------------------------------------------------------------------

    def get_workflow(self, workflow_id: str) -> GovernanceWorkflow:
        """查看单条工作流（只读）。"""
        return self._get_workflow(workflow_id)

    def list_workflows(
        self,
        *,
        org_id: Optional[str] = None,
        status: "Optional[GovernanceWorkflowStatus | str]" = None,
        user: Any = None,
        resource_category: str = "governance_workflow",
    ) -> List[GovernanceWorkflow]:
        """列出工作流（只读；组织隔离 + 可选权限闸门）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out: List[GovernanceWorkflow] = []
        for wf in self._workflows.values():
            scope = org_id or self._org_id
            if scope and wf.org_id and wf.org_id != scope:
                continue
            if status is not None:
                tgt = (
                    status
                    if isinstance(status, GovernanceWorkflowStatus)
                    else GovernanceWorkflowStatus(status)
                )
                if wf.status != tgt:
                    continue
            out.append(wf)
        return out

    def get_reviews(self, workflow_id: Optional[str] = None) -> List[GovernanceWorkflowReview]:
        if workflow_id is None:
            return list(self._reviews.values())
        return [r for r in self._reviews.values() if r.workflow_id == workflow_id]

    def get_execution_records(self, workflow_id: str) -> List[GovernanceExecutionRecord]:
        return list(self._executions.get(str(workflow_id).strip(), []))


__all__ = ["GovernanceWorkflowOrchestrator"]
