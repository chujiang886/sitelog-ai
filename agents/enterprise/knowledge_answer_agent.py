"""Enterprise Knowledge Agent Orchestration Layer —— 回答起草智能体（任务4，Phase 3.8.10）。

新增：``KnowledgeAnswerAgent``（AI 智能体）。

职责（红线严格限定）：
- 基于可追溯的 ``KnowledgeContext`` 与校验结果，产出 ``KnowledgeAnswerDraft``（调用
  Phase 3.8.9 的 ``KnowledgeAnswerService``）。
- 草稿**必须引用来源**（references 非空，由 ``KnowledgeAnswerDraft`` 在结构上保证），
  ``requires_human_review`` 强制为 True（红线⑥：AI 不得替代人工责任）。
- **绝不自动应用知识、绝不生成工程结论**（``auto_apply_knowledge`` /
  ``generate_engineering_conclusion`` 等决策入口在结构上被拦截，红线③/④/⑤）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 智能体默认 AI，红线⑥：绝不伪造为人工审批）。
"""

from __future__ import annotations

from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService
from agents.enterprise.knowledge_answer import (
    KnowledgeAnswerDraft,
    KnowledgeAnswerService,
)
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQuery
from agents.enterprise.knowledge_validation_agent import (
    KnowledgeAgentValidationResult,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class KnowledgeAnswerAgent(_RedLineForbiddenMixin):
    """回答起草智能体（任务4）。

    产出**带来源引用**的回答草稿，仅候选，**绝不**自动应用知识或生成工程结论。
    跨域访问由底层服务统一拦截；构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。

    本智能体**不**持有 approve / engineering_approved / auto_apply_knowledge /
    generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识
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
        answer_service: "KnowledgeAnswerService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeAnswerAgent（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._answer_service = answer_service or KnowledgeAnswerService(
            org_id=org_id,
            audit=audit,
            identity=identity,
            visibility=visibility,
        )

    def draft(
        self,
        *,
        answer_id: str,
        query: KnowledgeQuery,
        context: KnowledgeContext,
        validation: "KnowledgeAgentValidationResult | None" = None,
        content: str = "",
        confidence: float = 0.0,
        created_at: str = "",
        actor_id: str = "ai",
    ) -> KnowledgeAnswerDraft:
        """起草一份**带来源引用**的回答草稿（references = 上下文来源，requires_human_review 强制 True）。

        草稿仅候选，**绝不**自动应用知识或生成工程结论（red line ③/④/⑤）。
        如实记录 ``KNOWLEDGE_AGENT_DRAFT`` 审计（AI 智能体默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下起草回答（红线①/⑤）"
            )
        references = list(context.sources)
        draft = self._answer_service.draft_answer(
            answer_id=answer_id,
            query_id=query.query_id,
            references=references,
            content=content,
            confidence=confidence,
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=AuditActorKind.AI,
        )
        if self._audit is not None:
            self._audit.record_knowledge_agent_draft_action(
                record_id=f"agent-draft-{answer_id}",
                actor_id=actor_id,
                action="agent_draft_answer",
                target=answer_id,
                detail=(
                    f"query_id={query.query_id};references={len(references)};"
                    f"confidence={draft.confidence};requires_human_review=true"
                ),
                ts=created_at,
                actor_kind=AuditActorKind.AI,
            )
        return draft


__all__ = ["KnowledgeAnswerAgent"]
