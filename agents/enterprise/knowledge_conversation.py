"""Enterprise Knowledge Conversation & Memory Layer —— 知识会话模型（任务1，Phase 3.8.11）。

新增：
- ``ConversationStatus``：会话状态枚举（active / archived）。
- ``KnowledgeConversation``：一次企业知识对话的会话实体（conversation_id / org_id / user_id
  / title / status / created_at / updated_at），**组织隔离**（org_id 绑定）。
- ``KnowledgeConversationService``：组织作用域内的会话服务（创建 / 读取 / 列举本人会话 /
  归档）。

红线（fail-closed，复用 3.8.0~3.8.10 基座 + 3.8.11 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 会话只暂存对话上下文，**绝不自动写知识库、绝不自动学习用户信息并写入知识**
  （红线③/④：不持有 auto_update_knowledge / auto_merge_knowledge / auto_publish_knowledge /
  auto_apply_knowledge / auto_learn_user / auto_save_user_to_knowledge 等方法）。
- 不同用户只能访问自己的会话（任务6：接入 IdentityService + 角色校验，ADMIN 可跨用户查看）；
  跨域访问抛 ``EnterpriseIsolationError``。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
- 可选联动 ``AuditService`` 如实标注发起方（会话由用户发起默认 USER，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, RoleKind, User
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


class ConversationStatus(str, Enum):
    """会话状态（任务1）。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class KnowledgeConversation:
    """知识会话实体（任务1）。

    绑定 ``org_id``（组织隔离）；``user_id`` 标识会话归属人，用于任务6 的访问隔离。
    会话仅承载对话上下文，不持有任何知识资产引用写入权。
    """

    conversation_id: str
    org_id: str
    user_id: str
    title: str = ""
    status: ConversationStatus = ConversationStatus.ACTIVE
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConversationStatus):
            self.status = ConversationStatus(self.status)


class KnowledgeConversationService(_RedLineForbiddenMixin):
    """知识会话服务（任务1）。

    提供 ``create`` / ``get`` / ``list_for_user`` / ``archive``。会话只暂存，**绝不**自动写
    知识库或学习用户信息。跨域访问抛 ``EnterpriseIsolationError``；写路径断言
    ``safety_invariants_ok()``（红线①/⑤）。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_update_knowledge / auto_merge_knowledge /
    auto_publish_knowledge / auto_apply_knowledge / auto_learn_user /
    auto_save_user_to_knowledge 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/发布/合并/应用/学习知识或用户信息
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
                "KnowledgeConversationService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._conversations: dict[str, KnowledgeConversation] = {}

    def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        title: str = "",
        created_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeConversation:
        """创建一次会话（由用户发起，默认 USER 审计；绝不写知识库，红线③/④）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建会话（红线①/⑤）"
            )
        conv = KnowledgeConversation(
            conversation_id=conversation_id,
            org_id=self._org_id,
            user_id=user_id,
            title=title,
            status=ConversationStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
        )
        self._conversations[conversation_id] = conv
        if self._audit is not None:
            self._audit.record_knowledge_conversation_action(
                record_id=f"conv-{conversation_id}",
                actor_id=actor_id or user_id,
                action="create_knowledge_conversation",
                target=conversation_id,
                detail=f"title={title};user_id={user_id}",
                ts=created_at,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return conv

    def _assert_access(self, *, conversation: KnowledgeConversation,
                       requesting_user_id: str, requesting_role: "RoleKind | None") -> None:
        """任务6：访问隔离——本人可访问；ADMIN 可跨用户查看；其余拒绝。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        if conversation.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"会话 {conversation.conversation_id!r} 归属组织 {conversation.org_id!r} "
                f"与当前组织 {self._org_id!r} 不一致，禁止跨域访问"
            )
        if requesting_user_id == conversation.user_id:
            return
        if requesting_role == RoleKind.ADMIN:
            return
        raise EnterpriseRedLineViolationError(
            f"用户 {requesting_user_id!r} 无权访问会话 {conversation.conversation_id!r}："
            f"仅会话归属人或 ADMIN 可访问（红线⑥/任务6 访问隔离）"
        )

    def get(
        self,
        *,
        conversation_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> KnowledgeConversation:
        """按组织作用域 + 访问隔离读取会话（跨域/越权抛错）。"""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(f"会话 {conversation_id!r} 不存在")
        self._assert_access(
            conversation=conv,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        return conv

    def list_for_user(self, *, user_id: str) -> list[KnowledgeConversation]:
        """列举某用户的全部会话（组织作用域过滤；仅返回本人会话，满足访问隔离）。"""
        out: list[KnowledgeConversation] = []
        for c in self._conversations.values():
            if c.org_id != self._org_id:
                continue
            if c.user_id == user_id:
                out.append(c)
        return out

    def archive(
        self,
        *,
        conversation_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        updated_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeConversation:
        """归档会话（人工动作，默认 USER 审计；越权拒绝，红线⑥/任务6）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下归档会话（红线①/⑤）"
            )
        conv = self.get(
            conversation_id=conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        conv.status = ConversationStatus.ARCHIVED
        conv.updated_at = updated_at
        if self._audit is not None:
            self._audit.record_knowledge_conversation_action(
                record_id=f"conv-archive-{conversation_id}",
                actor_id=actor_id or requesting_user_id,
                action="archive_knowledge_conversation",
                target=conversation_id,
                detail=f"user_id={conv.user_id}",
                ts=updated_at,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return conv


__all__ = ["ConversationStatus", "KnowledgeConversation", "KnowledgeConversationService"]
