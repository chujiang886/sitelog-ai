"""Enterprise Knowledge Agent Orchestration Layer —— 检索智能体（任务2，Phase 3.8.10）。

新增：``KnowledgeRetrievalAgent``（AI 智能体）。

职责（红线严格限定）：
- 调用 ``KnowledgeRetrievalEngine``（Phase 3.8.9 检索引擎），产出**可追溯**的
  ``KnowledgeContext``；上下文中每条知识都自动派生 ``sources`` / ``versions`` / ``trace``，
  **确保所有召回知识可溯源**（任务2 核心要求）。
- 检索智能体**只召回候选知识**，绝不自动应用知识、绝不生成工程结论
  （``auto_apply_knowledge`` / ``generate_engineering_conclusion`` 等决策入口在结构上被拦截，
  红线③/④/⑤）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 智能体默认 AI，红线⑥：绝不伪造为人工审批）。
"""

from __future__ import annotations

from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQuery
from agents.enterprise.knowledge_retrieval import (
    KnowledgeItem,
    KnowledgeRetrievalEngine,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class KnowledgeRetrievalAgent(_RedLineForbiddenMixin):
    """检索智能体（任务2）。

    封装 ``KnowledgeRetrievalEngine``；``retrieve`` 产出可追溯的 ``KnowledgeContext``。
    跨域访问由引擎统一拦截；构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。

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
        engine: "KnowledgeRetrievalEngine | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeRetrievalAgent（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)
        self._engine = engine or KnowledgeRetrievalEngine(
            org_id=org_id,
            audit=audit,
            identity=identity,
            visibility=self._visibility,
        )

    def retrieve(
        self,
        *,
        query: KnowledgeQuery,
        role: "RoleKind | None" = None,
        top_k: int = 5,
        actor_id: str = "ai",
    ) -> KnowledgeContext:
        """根据用户查询召回**可追溯**的检索上下文（仅候选，不落地、不生成结论，红线③/④/⑤）。

        流程：① 调用引擎语义检索（含权限过滤 + 业务过滤）→ ② 用召回结果拼装
        ``KnowledgeContext``（自动派生 sources/versions/trace，确保溯源）。

        如实记录 ``KNOWLEDGE_AGENT_RETRIEVE`` 审计（AI 智能体默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行智能体检索（红线①/⑤）"
            )
        items: list[KnowledgeItem] = self._engine.search(
            query_text=query.raw_query,
            role=role,
            filters=query.filters,
            top_k=top_k,
        )
        ctx = self._engine.retrieve_context(
            query_id=query.query_id,
            items=items,
            org_id=self._org_id,
        )
        if self._audit is not None:
            self._audit.record_knowledge_agent_retrieve_action(
                record_id=f"agent-retrieve-{query.query_id}",
                actor_id=actor_id,
                action="agent_retrieve_knowledge",
                target=query.query_id,
                detail=(
                    f"matched={len(items)};context_items={len(ctx.knowledge_items)};"
                    f"source_gaps={ctx.has_source_gaps()}"
                ),
                actor_kind=AuditActorKind.AI,
            )
        return ctx


__all__ = ["KnowledgeRetrievalAgent"]
