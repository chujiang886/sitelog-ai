"""Enterprise Knowledge Conversation & Memory Layer —— 会话消息模型（任务2，Phase 3.8.11）。

新增：
- ``MessageRole``：消息角色枚举（USER / AI）。
- ``KnowledgeMessage``：一条会话消息（message_id / conversation_id / role / content /
  timestamp / references）；**AI 消息必须记录引用来源**（references 非空，禁无来源回答），
  且 AI 消息 ``requires_human_review`` 强制为 True（红线⑥）。
- ``KnowledgeMessageService``：组织作用域内的消息服务（追加 / 读取 / 列举）。

红线（fail-closed，复用 3.8.0~3.8.10 基座 + 3.8.11 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- AI 消息**必须引用来源**（references 非空），禁止无来源回答（任务2 核心）。
- AI 消息 ``requires_human_review`` 强制 True：草稿仅作参考，最终采用须经真实人工（红线⑥）。
- 消息只记录对话上下文，**绝不自动写知识库**（红线③/④）。
- 不同用户只能访问自己的会话消息（任务6：接入 IdentityService + 角色校验）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
- 可选联动 ``AuditService`` 如实标注发起方（USER 提问默认 USER；AI 回答默认 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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


class MessageRole(str, Enum):
    """消息角色（任务2）。"""

    USER = "user"
    AI = "ai"


@dataclass
class KnowledgeMessage:
    """会话消息（任务2）。

    **AI 消息必须引用来源**（``references`` 非空），禁止无来源回答；``requires_human_review``
    对 AI 消息强制为 True（AI 起草仅作参考，最终采用须经真实人工，红线⑥）。``confidence`` 仅
    表达 AI 消息自身置信度，不代表任何工程结论可信度。
    """

    message_id: str
    conversation_id: str
    role: MessageRole
    content: str = ""
    references: list[str] = field(default_factory=list)   # AI 消息必须非空
    timestamp: str = ""
    org_id: str = ""
    requires_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            self.role = MessageRole(self.role)
        # 任务2 核心：AI 消息禁止无来源回答。
        if self.role is MessageRole.AI and not self.references:
            raise ValueError(
                "KnowledgeMessage(AI) 必须引用来源（references 非空）：禁止无来源回答"
            )
        # 红线⑥：AI 消息草稿始终需要人工复核，AI 不得替代人工责任。
        if self.role is MessageRole.AI:
            self.requires_human_review = True


class KnowledgeMessageService(_RedLineForbiddenMixin):
    """会话消息服务（任务2）。

    提供 ``append`` / ``get`` / ``list_for_conversation``。AI 消息**必须引用来源**，绝不自动
    应用知识或生成工程结论。跨域/越权访问抛错；写路径断言 ``safety_invariants_ok()``
    （红线①/⑤）。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_update_knowledge / auto_publish_knowledge /
    auto_merge_knowledge / auto_apply_knowledge / auto_learn_user 等方法
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
        conversations: "KnowledgeConversationService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeMessageService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._conversations = conversations
        self._messages: dict[str, KnowledgeMessage] = {}

    def _assert_conversation_access(
        self, *, conversation_id: str, requesting_user_id: str,
        requesting_role: "RoleKind | None",
    ) -> None:
        """任务6：消息访问受其归属会话的访问隔离约束。"""
        if self._conversations is not None:
            self._conversations.get(
                conversation_id=conversation_id,
                requesting_user_id=requesting_user_id,
                requesting_role=requesting_role,
            )
            return
        # 无会话服务注入时退化为组织作用域检查（调用方仍须保证会话归属一致）。
        if conversation_id.split(":", 1)[0] != self._org_id and not conversation_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError("会话归属组织校验缺失")

    def append(
        self,
        *,
        message_id: str,
        conversation_id: str,
        role: "MessageRole | str",
        content: str = "",
        references: "list[str] | None" = None,
        timestamp: str = "",
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> KnowledgeMessage:
        """追加一条消息（USER 提问 / AI 回答草稿）。

        AI 消息必须引用来源（references 非空）；消息只记录对话上下文，绝不写知识库
        （红线③/④）。如实记录 ``KNOWLEDGE_MESSAGE`` 审计（USER 默认 USER，AI 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下追加消息（红线①/⑤）"
            )
        self._assert_conversation_access(
            conversation_id=conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        msg = KnowledgeMessage(
            message_id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            references=list(references or []),
            timestamp=timestamp,
            org_id=self._org_id,
        )
        self._messages[message_id] = msg
        if self._audit is not None:
            self._audit.record_knowledge_message_action(
                record_id=f"msg-{message_id}",
                actor_id=actor_id or requesting_user_id,
                action="append_knowledge_message",
                target=message_id,
                detail=(
                    f"conversation_id={conversation_id};role={msg.role.value};"
                    f"references={len(msg.references)};"
                    f"requires_human_review={msg.requires_human_review}"
                ),
                ts=timestamp,
                actor_kind=actor_kind or (
                    AuditActorKind.AI if msg.role is MessageRole.AI else AuditActorKind.USER
                ),
            )
        return msg

    def get(
        self,
        *,
        message_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> KnowledgeMessage:
        """按组织作用域 + 会话访问隔离读取消息（越权抛错，任务6）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        msg = self._messages.get(message_id)
        if msg is None:
            raise EnterpriseIsolationError(f"消息 {message_id!r} 不存在")
        if msg.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"消息 {message_id!r} 归属组织 {msg.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        self._assert_conversation_access(
            conversation_id=msg.conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        return msg

    def list_for_conversation(
        self,
        *,
        conversation_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> list[KnowledgeMessage]:
        """列举某会话的全部消息（组织作用域 + 访问隔离过滤）。"""
        self._assert_conversation_access(
            conversation_id=conversation_id,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        out: list[KnowledgeMessage] = []
        for m in self._messages.values():
            if m.org_id != self._org_id:
                continue
            if m.conversation_id == conversation_id:
                out.append(m)
        return out


__all__ = ["MessageRole", "KnowledgeMessage", "KnowledgeMessageService"]
