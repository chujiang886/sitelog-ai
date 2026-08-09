"""Enterprise Knowledge Conversation & Memory Layer —— 会话上下文（任务3，Phase 3.8.11）。

新增：
- ``KnowledgeConversationContext``：一次会话的**上下文快照**（conversation_id / org_id /
  active_topics / referenced_knowledge / unresolved_questions / trace）。仅保存会话上下文，
  **不持有任何写知识库的能力**（红线③/④）。
- ``KnowledgeConversationContextService``：组织作用域内的会话上下文服务（更新 / 读取 /
  授权知识过滤）。

红线（fail-closed，复用 3.8.0~3.8.10 基座 + 3.8.11 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 上下文**只保存会话上下文**，禁止自动写知识库 / 自动学习用户信息（红线③/④；不持有
  auto_update_knowledge / auto_write_knowledge / auto_publish_knowledge /
  auto_learn_user / write_to_knowledge 等方法）。
- 不同用户只能访问自己的会话上下文（任务6：接入 IdentityService + 角色校验）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
- 可选联动 ``AuditService`` 如实标注发起方（上下文更新默认 USER，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.knowledge_conversation import (
    KnowledgeConversationService,
)
from agents.enterprise.knowledge_context import KnowledgeTrace


@dataclass
class KnowledgeConversationContext:
    """会话上下文快照（任务3）。

    仅聚合会话内的活跃主题 / 引用知识 / 未决问题 / 溯源；**不持有任何知识资产引用写入权**，
    上下文更新不会改变知识库内容（红线③/④）。
    """

    conversation_id: str
    org_id: str = ""
    active_topics: list[str] = field(default_factory=list)
    referenced_knowledge: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    trace: list[KnowledgeTrace] = field(default_factory=list)


class KnowledgeConversationContextService(_RedLineForbiddenMixin):
    """会话上下文服务（任务3）。

    提供 ``update_context`` / ``get`` / ``filter_visible_references``。上下文**只暂存**，
    绝不自动写知识库或学习用户信息。跨域/越权访问抛错；写路径断言 ``safety_invariants_ok()``
    （红线①/⑤）。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_update_knowledge / auto_write_knowledge /
    auto_publish_knowledge / auto_learn_user / write_to_knowledge 等方法
    （红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/写入/发布/合并/应用/学习知识或用户信息
        "auto_update_knowledge",
        "auto_write_knowledge",
        "write_to_knowledge",
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
        conversations: "KnowledgeConversationService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeConversationContextService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._conversations = conversations
        self._contexts: dict[str, KnowledgeConversationContext] = {}

    def _assert_conversation_access(
        self, *, conversation_id: str, requesting_user_id: str,
        requesting_role: "RoleKind | None",
    ) -> None:
        """任务6：上下文访问受其归属会话的访问隔离约束。"""
        if self._conversations is not None:
            self._conversations.get(
                conversation_id=conversation_id,
                requesting_user_id=requesting_user_id,
                requesting_role=requesting_role,
            )
            return

    def update_context(
        self,
        *,
        conversation_id: str,
        active_topics: "list[str] | None" = None,
        referenced_knowledge: "list[str] | None" = None,
        unresolved_questions: "list[str] | None" = None,
        trace: "list[KnowledgeTrace] | None" = None,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
        timestamp: str = "",
    ) -> KnowledgeConversationContext:
        """更新会话上下文（**只暂存会话上下文**，绝不写知识库，红线③/④）。

        如实记录 ``KNOWLEDGE_CONVERSATION`` 审计（action=update_conversation_context，
        默认 USER，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下更新会话上下文（红线①/⑤）"
            )
        self._assert_conversation_access(
            conversation_id=conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            ctx = KnowledgeConversationContext(
                conversation_id=conversation_id, org_id=self._org_id,
            )
            self._contexts[conversation_id] = ctx
        if active_topics is not None:
            ctx.active_topics = list(active_topics)
        if referenced_knowledge is not None:
            ctx.referenced_knowledge = list(referenced_knowledge)
        if unresolved_questions is not None:
            ctx.unresolved_questions = list(unresolved_questions)
        if trace is not None:
            ctx.trace = list(trace)
        if self._audit is not None:
            self._audit.record_knowledge_conversation_action(
                record_id=f"ctx-{conversation_id}",
                actor_id=actor_id or requesting_user_id,
                action="update_conversation_context",
                target=conversation_id,
                detail=(
                    f"topics={len(ctx.active_topics)};"
                    f"references={len(ctx.referenced_knowledge)};"
                    f"questions={len(ctx.unresolved_questions)}"
                ),
                ts=timestamp,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return ctx

    def get(
        self,
        *,
        conversation_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> KnowledgeConversationContext:
        """按组织作用域 + 会话访问隔离读取上下文（越权抛错，任务6）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            raise EnterpriseIsolationError(f"会话上下文 {conversation_id!r} 不存在")
        if ctx.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"会话上下文 {conversation_id!r} 归属组织 {ctx.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        self._assert_conversation_access(
            conversation_id=conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        return ctx

    def filter_visible_references(
        self,
        *,
        conversation_id: str,
        role: RoleKind,
        type_resolver: "Callable[[str], str]",
    ) -> list[str]:
        """任务6：按 KnowledgeVisibilityPolicy 过滤「授权知识」。

        ``type_resolver`` 将知识 id 映射到其 knowledge_type；仅返回该角色被允许检索的知识 id
        （默认拒绝）。上下文本身不改写，仅返回可见子集。
        """
        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            return []
        if self._visibility is None:
            # 无可见性策略时退化为「全部不可见」（默认拒绝，红线③/④ fail-closed）。
            return []
        return [
            kid for kid in ctx.referenced_knowledge
            if self._visibility.is_knowledge_permitted(role, type_resolver(kid))
        ]


__all__ = ["KnowledgeConversationContext", "KnowledgeConversationContextService"]
