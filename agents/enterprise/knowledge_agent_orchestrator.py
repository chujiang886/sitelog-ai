"""Enterprise Knowledge Agent Orchestration Layer —— 智能体编排器（任务5，Phase 3.8.10）。

新增：``KnowledgeAgentOrchestrator``（编排门面）+ ``KnowledgeAgentEvent``。

职责（红线严格限定）：
- 串起四个 AI 智能体的完整闭环：``query``（理解）→ ``retrieve``（召回可追溯上下文）
  → ``validate``（校验）→ ``draft``（起草待复核草稿）。
- 全程记录 ``agent_event_log``（每一步骤事件：step / agent / status / detail / ts），
  供审计与人工复核回溯。
- 四个子智能体共享同一 ``audit`` / ``identity`` / ``visibility`` 实例（与聚合层约定一致）。
- **绝不**在编排层做任何批准 / 落地 / 结论生成；最终采用必须经真实人工复核（红线②/③/④/⑥）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_answer_agent import KnowledgeAnswerAgent
from agents.enterprise.knowledge_answer import KnowledgeAnswerDraft
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQuery, KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval_agent import KnowledgeRetrievalAgent
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
class KnowledgeAgentEvent:
    """智能体编排事件（任务5）。

    记录编排闭环中每一步骤的事实事件；仅描述「哪个智能体做了哪一步、状态如何」，
    不承载任何批准 / 落地 / 结论语义（红线②/③/④/⑥）。
    """

    event_id: str
    step: str               # query / retrieve / validate / draft
    agent: str
    status: str             # ok / skipped / failed
    detail: str = ""
    ts: str = ""


class KnowledgeAgentOrchestrator(_RedLineForbiddenMixin):
    """知识智能体编排器（任务5）。

    把 Query / Retrieve / Validate / Draft 四个 AI 智能体串成闭环，并记录
    ``agent_event_log``。所有子智能体共享同一 ``audit`` / ``identity`` / ``visibility``。

    本编排器**不**持有任何批准/报价/审批/记录为人工/自动应用知识方法（红线②/③/④/⑥）；
    最终回答采用必须经真实人工复核（由下游 ``KnowledgeAnswerReview`` 强制要求）。

    为统一红线姿态，编排器同样继承 ``_RedLineForbiddenMixin``：即便将来新增编排方法，
    任何批准/报价/审批/自动应用知识/生成工程结论入口也会在结构上被拦截（防御性 fail-closed）。
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
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeAgentOrchestrator（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)
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
        self._events: list[KnowledgeAgentEvent] = []

    def run(
        self,
        *,
        query_id: str,
        raw_query: str,
        answer_id: str,
        role: "RoleKind | None" = None,
        top_k: int = 5,
        parsed_at: str = "",
        created_at: str = "",
        content: str = "",
        confidence: float = 0.0,
        actor_id: str = "ai",
    ) -> KnowledgeAnswerDraft:
        """执行完整编排闭环：query → retrieve → validate → draft。

        返回**待人工复核**的回答草稿（requires_human_review 强制 True）。
        全程写入 ``agent_event_log``。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下运行编排器（红线①/⑤）"
            )

        # ① Query：理解用户需求
        query: KnowledgeQuery = self._query_agent.parse_query(
            query_id=query_id,
            raw_query=raw_query,
            parsed_at=parsed_at,
            actor_id=actor_id,
        )
        self._log_event(
            event_id=f"ev-query-{query_id}",
            step="query",
            agent="KnowledgeQueryAgent",
            status="ok",
            detail=f"intent={query.intent}",
            ts=parsed_at,
        )

        # ② Retrieve：召回可追溯上下文
        context: KnowledgeContext = self._retrieval_agent.retrieve(
            query=query, role=role, top_k=top_k, actor_id=actor_id
        )
        self._log_event(
            event_id=f"ev-retrieve-{query_id}",
            step="retrieve",
            agent="KnowledgeRetrievalAgent",
            status="ok",
            detail=f"context_items={len(context.knowledge_items)}",
            ts=parsed_at,
        )

        # ③ Validate：四维校验（不批准）
        validation: KnowledgeAgentValidationResult = self._validation_agent.validate(
            validation_id=f"val-{query_id}",
            query=query,
            context=context,
            role=role,
            actor_id=actor_id,
        )
        self._log_event(
            event_id=f"ev-validate-{query_id}",
            step="validate",
            agent="KnowledgeValidationAgent",
            status="ok",
            detail=f"passed={validation.passed};issues={len(validation.issues)}",
            ts=parsed_at,
        )

        # ④ Draft：起草待复核草稿
        draft: KnowledgeAnswerDraft = self._answer_agent.draft(
            answer_id=answer_id,
            query=query,
            context=context,
            validation=validation,
            content=content,
            confidence=confidence,
            created_at=created_at,
            actor_id=actor_id,
        )
        self._log_event(
            event_id=f"ev-draft-{answer_id}",
            step="draft",
            agent="KnowledgeAnswerAgent",
            status="ok",
            detail=f"references={len(draft.references)}",
            ts=created_at,
        )
        return draft

    def agent_event_log(self) -> list[KnowledgeAgentEvent]:
        """返回本次会话内编排事件的不可变副本（供审计 / 人工复核回溯）。"""
        return list(self._events)

    def _log_event(
        self,
        *,
        event_id: str,
        step: str,
        agent: str,
        status: str,
        detail: str,
        ts: str,
    ) -> None:
        self._events.append(
            KnowledgeAgentEvent(
                event_id=event_id,
                step=step,
                agent=agent,
                status=status,
                detail=detail,
                ts=ts,
            )
        )


__all__ = ["KnowledgeAgentEvent", "KnowledgeAgentOrchestrator"]
