"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 多智能体工作流编排器（任务4，Phase 3.8.12）。

新增：``KnowledgeTaskOrchestrator``（任务编排门面）+ ``KnowledgeTaskWorkflowEvent``。

职责（红线严格限定）：
- 串起「用户问题 → 任务拆解（Planner）→ Agent 规划（retrieval/validation/analysis/draft）
  → 知识调用 → 结果汇总」的完整闭环；复用 Phase 3.8.10 的 Query/Retrieve/Validate/Answer
  四个 AI 智能体。
- 编排器**只协调、不审批、不落地工程结论**（红线②/③/④/⑥）：最终任务进入 ``waiting_review``，
  ``requires_human_review`` 强制为 True（任务5），绝不自动标 ``completed``。
- 全程记录 ``task_workflow_event_log``（每步事实事件）供人工复核回溯。
- 任务7：各 Agent 共享同一 ``visibility``，检索阶段自动按角色过滤（知识可见性策略）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_answer import KnowledgeAnswerDraft
from agents.enterprise.knowledge_answer_agent import KnowledgeAnswerAgent
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQuery, KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval_agent import KnowledgeRetrievalAgent
from agents.enterprise.knowledge_subtask import (
    KnowledgeSubTaskService,
    KnowledgeSubTaskType,
)
from agents.enterprise.knowledge_task import (
    KnowledgeTaskService,
    KnowledgeTaskStatus,
)
from agents.enterprise.knowledge_task_planner import KnowledgeTaskPlanner
from agents.enterprise.knowledge_validation_agent import (
    KnowledgeAgentValidationResult,
    KnowledgeValidationAgent,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


@dataclass
class KnowledgeTaskWorkflowEvent:
    """任务工作流事件（任务4）。

    记录编排闭环中每一步骤的事实事件；仅描述「哪一步、哪个 Agent、状态如何」，不承载任何批准 /
    落地 / 结论语义（红线②/③/④/⑥）。
    """

    event_id: str
    step: str               # plan / query / retrieve / validate / analyze / draft / review
    agent: str
    status: str             # ok / skipped / failed
    detail: str = ""
    ts: str = ""


class KnowledgeTaskOrchestrator(_RedLineForbiddenMixin):
    """知识任务多智能体编排器（任务4）。

    把 Planner + 四个 AI 智能体串成闭环，并记录 ``task_workflow_event_log``。所有子组件共享同一
    ``audit`` / ``identity`` / ``visibility``。

    本编排器**不**持有任何批准/报价/审批/记录为人工/自动应用知识/生成工程结论方法
    （红线②/③/④/⑥）；最终任务须经真实人工复核（由 TaskReviewCheckpoint 强制）。

    为统一红线姿态，编排器同样继承 ``_RedLineForbiddenMixin``：任何批准/报价/审批/自动应用知识/
    生成工程结论入口也会在结构上被拦截（防御性 fail-closed）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_apply_knowledge",
        "auto_execute_knowledge",
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_activate",
        "publish",
        "merge",
        "apply",
        "commit",
        "write",
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
        subtask_service: "KnowledgeSubTaskService | None" = None,
        planner: "KnowledgeTaskPlanner | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeTaskOrchestrator（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)
        self._task_service = task_service or KnowledgeTaskService(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._subtask_service = subtask_service or KnowledgeSubTaskService(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._planner = planner or KnowledgeTaskPlanner(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._query_agent = KnowledgeQueryAgent(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._retrieval_agent = KnowledgeRetrievalAgent(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._validation_agent = KnowledgeValidationAgent(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._answer_agent = KnowledgeAnswerAgent(
            org_id=org_id, audit=audit, identity=identity, visibility=self._visibility
        )
        self._events: list[KnowledgeTaskWorkflowEvent] = []

    def run_task(
        self,
        *,
        task_id: str,
        goal: str,
        user_id: str,
        conversation_id: str,
        role: "RoleKind | None" = None,
        top_k: int = 5,
        created_at: str = "",
        content: str = "",
        confidence: float = 0.0,
        actor_id: str = "ai",
    ) -> KnowledgeAnswerDraft:
        """执行完整任务编排闭环：plan → query → retrieve → validate →[analyze]→ draft。

        返回**待人工复核**的回答草稿（requires_human_review 强制 True）；任务进入
        ``waiting_review``，**绝不**自动标 ``completed``（任务5/红线⑥）。

        注意：调用方须确保 ``task_id`` 对应任务已由用户创建（KnowledgeTaskService.create，
        USER 审计）。本方法只做规划与 Agent 协调。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下运行任务编排器（红线①/⑤）"
            )

        # ① plan：规划（只拆任务，不决策）
        plan = self._planner.create_plan(goal, task_id=task_id, role=role)
        self._task_service.update_plan(
            task_id=task_id,
            steps=plan.steps,
            requesting_user_id=user_id,
            updated_at=created_at,
            actor_id=actor_id,
            actor_kind=AuditActorKind.AI,
        )
        self._log_event(
            event_id=f"tw-plan-{task_id}", step="plan", agent="KnowledgeTaskPlanner",
            status="ok", detail=f"complexity={plan.complexity};subtasks={len(plan.subtasks)}",
            ts=created_at,
        )

        # ② query：理解用户需求
        query: KnowledgeQuery = self._query_agent.parse_query(
            query_id=f"q-{task_id}", raw_query=goal, parsed_at=created_at, actor_id=actor_id
        )
        self._log_event(
            event_id=f"tw-query-{task_id}", step="query", agent="KnowledgeQueryAgent",
            status="ok", detail=f"intent={query.intent}", ts=created_at,
        )

        # ③ retrieve：召回可追溯上下文（按角色可见性过滤）
        context: KnowledgeContext = self._retrieval_agent.retrieve(
            query=query, role=role, top_k=top_k, actor_id=actor_id
        )
        self._subtask_service.create(
            subtask_id=f"{task_id}-s1", task_id=task_id,
            agent_type=KnowledgeSubTaskType.RETRIEVAL,
            input={"goal": goal}, created_at=created_at, actor_id=actor_id,
        )
        self._subtask_service.complete(
            subtask_id=f"{task_id}-s1",
            output={"context_items": len(context.knowledge_items)},
            updated_at=created_at, actor_id=actor_id,
        )
        self._log_event(
            event_id=f"tw-retrieve-{task_id}", step="retrieve",
            agent="KnowledgeRetrievalAgent", status="ok",
            detail=f"context_items={len(context.knowledge_items)}", ts=created_at,
        )

        # ④ validate：四维校验（不批准）
        validation: KnowledgeAgentValidationResult = self._validation_agent.validate(
            validation_id=f"val-{task_id}", query=query, context=context, role=role,
            actor_id=actor_id,
        )
        self._subtask_service.create(
            subtask_id=f"{task_id}-s2", task_id=task_id,
            agent_type=KnowledgeSubTaskType.VALIDATION,
            input={"goal": goal}, created_at=created_at, actor_id=actor_id,
        )
        self._subtask_service.complete(
            subtask_id=f"{task_id}-s2",
            output={"passed": validation.passed, "issues": len(validation.issues)},
            updated_at=created_at, actor_id=actor_id,
        )
        self._log_event(
            event_id=f"tw-validate-{task_id}", step="validate",
            agent="KnowledgeValidationAgent", status="ok",
            detail=f"passed={validation.passed};issues={len(validation.issues)}",
            ts=created_at,
        )

        analysis_output: dict = {}
        # ⑤ analyze（仅当计划含 analysis 子任务）：内部结构化分析（中间态，非结论）
        analysis_specs = [s for s in plan.subtasks
                          if s.agent_type is KnowledgeSubTaskType.ANALYSIS]
        for spec in analysis_specs:
            analysis_output = {
                "validated_items": len(context.knowledge_items),
                "passed": validation.passed,
                "issues": len(validation.issues),
            }
            self._subtask_service.create(
                subtask_id=spec.subtask_id, task_id=task_id,
                agent_type=KnowledgeSubTaskType.ANALYSIS,
                input=spec.input, created_at=created_at, actor_id=actor_id,
            )
            self._subtask_service.complete(
                subtask_id=spec.subtask_id, output=analysis_output,
                updated_at=created_at, actor_id=actor_id,
            )
            self._log_event(
                event_id=f"tw-analyze-{spec.subtask_id}", step="analyze",
                agent="KnowledgeTaskOrchestrator(internal)", status="ok",
                detail=f"items={analysis_output['validated_items']}",
                ts=created_at,
            )

        # ⑥ draft：起草待复核草稿
        draft_idx = len(plan.subtasks)
        draft: KnowledgeAnswerDraft = self._answer_agent.draft(
            answer_id=f"a-{task_id}", query=query, context=context, validation=validation,
            content=content, confidence=confidence, created_at=created_at,
            actor_id=actor_id,
        )
        self._subtask_service.create(
            subtask_id=f"{task_id}-s{draft_idx}", task_id=task_id,
            agent_type=KnowledgeSubTaskType.DRAFT,
            input={"goal": goal}, created_at=created_at, actor_id=actor_id,
        )
        self._subtask_service.complete(
            subtask_id=f"{task_id}-s{draft_idx}",
            output={"references": len(draft.references)},
            updated_at=created_at, actor_id=actor_id,
        )
        self._log_event(
            event_id=f"tw-draft-{task_id}", step="draft", agent="KnowledgeAnswerAgent",
            status="ok", detail=f"references={len(draft.references)}", ts=created_at,
        )

        # ⑦ review gate（任务5/红线⑥）：复杂任务强制人工复核，绝不自动完成。
        requires_human_review = plan.requires_human_review
        task = self._task_service.get(
            task_id=task_id, requesting_user_id=user_id, requesting_role=role,
        )
        task.requires_human_review = requires_human_review or task.requires_human_review
        draft.requires_human_review = True  # 回答草稿恒待人工复核（3.8.10 结构保证 + 此处显式）
        # 任务进入 waiting_review，不自动 completed（红线⑥）
        self._task_service.advance_status(
            task_id=task_id, status=KnowledgeTaskStatus.WAITING_REVIEW,
            requesting_user_id=user_id, updated_at=created_at,
            actor_id=actor_id, actor_kind=AuditActorKind.AI,
        )
        self._log_event(
            event_id=f"tw-review-{task_id}", step="review",
            agent="TaskReviewCheckpoint", status="ok",
            detail=f"requires_human_review={draft.requires_human_review}", ts=created_at,
        )

        if self._audit is not None:
            self._audit.record_knowledge_agent_workflow_action(
                record_id=f"wf-{task_id}", actor_id=actor_id,
                action="run_knowledge_agent_workflow", target=task_id,
                detail=(
                    f"goal={goal};user_id={user_id};agents="
                    f"query,retrieve,validate"
                    f"{',analysis' if analysis_specs else ''},draft;"
                    f"requires_human_review={draft.requires_human_review}"
                ),
                ts=created_at, actor_kind=AuditActorKind.AI,
            )
        return draft

    def task_workflow_event_log(self) -> list[KnowledgeTaskWorkflowEvent]:
        """返回本次会话内编排事件的不可变副本（供审计 / 人工复核回溯）。"""
        return list(self._events)

    def _log_event(
        self, *, event_id: str, step: str, agent: str, status: str, detail: str, ts: str,
    ) -> None:
        self._events.append(
            KnowledgeTaskWorkflowEvent(
                event_id=event_id, step=step, agent=agent, status=status,
                detail=detail, ts=ts,
            )
        )


__all__ = ["KnowledgeTaskWorkflowEvent", "KnowledgeTaskOrchestrator"]
