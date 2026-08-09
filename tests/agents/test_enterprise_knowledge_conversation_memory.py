"""Enterprise Knowledge Conversation & Memory Layer —— 测试（任务7，Phase 3.8.11）。

覆盖 7 类：
1. conversation 模型（创建/读取/列举本人/归档，组织隔离）
2. message 模型（USER 提问 / AI 回答草稿；AI 必须引用来源；读取/列举）
3. conversation context（更新/读取；仅暂存会话上下文，不写知识库）
4. memory policy（AI 提议候选 requires_human_review=True；纳入须经真实 USER；禁止 AI 自动保存）
5. permission 接入（不同用户只能访问自己的会话；ADMIN 可跨用户；越权拒绝）
6. 会话审计（KNOWLEDGE_CONVERSATION / KNOWLEDGE_MESSAGE / KNOWLEDGE_MEMORY 如实记录 actor）
7. 红线（forbidden 方法被拦截；safety_invariants_ok；无 engineering_approved；无自动写知识）
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActorKind, AuditActionCategory
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise import (
    ConversationStatus,
    MessageRole,
    MemoryCandidateStatus,
    EnterpriseOperationLayer,
)


def _layer(org_id: str = "org-1") -> EnterpriseOperationLayer:
    return EnterpriseOperationLayer(org_id=org_id)


# ---- 1. conversation 模型 ----

def test_conversation_create_get_list_archive() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(
        conversation_id="c1", user_id="u1", title="风压规范咨询", created_at="t0",
    )
    conv = layer.knowledge_conversations.get(
        conversation_id="c1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert conv.conversation_id == "c1"
    assert conv.user_id == "u1"
    assert conv.status is ConversationStatus.ACTIVE
    assert conv.title == "风压规范咨询"

    mine = layer.knowledge_conversations.list_for_user(user_id="u1")
    assert len(mine) == 1

    archived = layer.knowledge_conversations.archive(
        conversation_id="c1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
        updated_at="t1",
    )
    assert archived.status is ConversationStatus.ARCHIVED


def test_conversation_org_isolation() -> None:
    l1 = _layer("org-A")
    l2 = _layer("org-B")
    l1.knowledge_conversations.create(conversation_id="ca", user_id="u1")
    # org-B 的 layer 完全看不到 org-A 的会话（组织隔离）。
    assert l2.knowledge_conversations.list_for_user(user_id="u1") == []


# ---- 2. message 模型 ----

def test_message_user_and_ai_append() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    layer.knowledge_messages.append(
        message_id="m1", conversation_id="c1", role=MessageRole.USER,
        content="开窗面积怎么算？", requesting_user_id="u1",
        requesting_role=RoleKind.DESIGNER, timestamp="t1",
    )
    # AI 消息必须引用来源
    ai_msg = layer.knowledge_messages.append(
        message_id="m2", conversation_id="c1", role=MessageRole.AI,
        content="依据 GB50009 计算。", references=["kb:wind-1", "kb:code-3"],
        requesting_user_id="u1", requesting_role=RoleKind.DESIGNER, timestamp="t2",
    )
    assert ai_msg.requires_human_review is True
    msgs = layer.knowledge_messages.list_for_conversation(
        conversation_id="c1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert len(msgs) == 2


def test_message_ai_requires_references() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    with pytest.raises(ValueError):
        layer.knowledge_messages.append(
            message_id="mX", conversation_id="c1", role=MessageRole.AI,
            content="无来源回答", references=[], requesting_user_id="u1",
            requesting_role=RoleKind.DESIGNER,
        )


# ---- 3. conversation context ----

def test_conversation_context_update_and_read() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    ctx = layer.knowledge_conversation_context.update_context(
        conversation_id="c1",
        active_topics=["风压", "开窗面积"],
        referenced_knowledge=["kb:wind-1", "kb:code-3"],
        unresolved_questions=["是否需专家复核？"],
        requesting_user_id="u1", requesting_role=RoleKind.DESIGNER, timestamp="t1",
    )
    assert ctx.active_topics == ["风压", "开窗面积"]
    assert ctx.referenced_knowledge == ["kb:wind-1", "kb:code-3"]
    got = layer.knowledge_conversation_context.get(
        conversation_id="c1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert got.unresolved_questions == ["是否需专家复核？"]


def test_conversation_context_only_session_no_knowledge_write() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    layer.knowledge_conversation_context.update_context(
        conversation_id="c1", referenced_knowledge=["kb:wind-1"],
        requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    # 上下文更新不得产生任何「知识候选 / 知识变更」副作用：本层不持有写知识库方法。
    svc = layer.knowledge_conversation_context
    for forbidden in ("auto_update_knowledge", "auto_write_knowledge",
                      "write_to_knowledge", "auto_publish_knowledge"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, forbidden)


# ---- 4. memory policy ----

def test_memory_propose_requires_human_review() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    cand = layer.knowledge_memory_policy.propose_long_term_memory(
        candidate_id="mem1", conversation_id="c1", user_id="u1",
        content="用户偏好用 GB50009 计算风压",
        source_references=["kb:wind-1"], created_at="t1",
    )
    # 红线⑥：候选 requires_human_review 强制 True，状态为 PROPOSED
    assert cand.requires_human_review is True
    assert cand.status is MemoryCandidateStatus.PROPOSED


def test_memory_commit_requires_real_user() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    layer.knowledge_memory_policy.propose_long_term_memory(
        candidate_id="mem1", conversation_id="c1", user_id="u1",
        content="用户偏好用 GB50009 计算风压",
        source_references=["kb:wind-1"], created_at="t1",
    )
    # AI 代 commit 必须被拒绝（红线⑥ human-gating）
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_memory_policy.commit_long_term_memory(
            candidate_id="mem1", requesting_user_id="u1",
            actor_kind=AuditActorKind.AI, committed_at="t2",
        )
    # 真实 USER 纳入成功
    committed = layer.knowledge_memory_policy.commit_long_term_memory(
        candidate_id="mem1", requesting_user_id="u1",
        requesting_role=RoleKind.DESIGNER, committed_at="t2",
        actor_kind=AuditActorKind.USER,
    )
    assert committed.status is MemoryCandidateStatus.COMMITTED
    assert committed.committed_by == "u1"


def test_memory_no_auto_save_knowledge() -> None:
    layer = _layer()
    svc = layer.knowledge_memory_policy
    for forbidden in ("auto_save_knowledge", "auto_update_knowledge",
                      "auto_publish_knowledge", "auto_learn_user", "commit"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, forbidden)


# ---- 5. permission 接入 ----

def test_permission_cross_user_denied_but_admin_allowed() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    # 不同普通用户越权访问 → 拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_conversations.get(
            conversation_id="c1", requesting_user_id="u2",
            requesting_role=RoleKind.DESIGNER,
        )
    # ADMIN 可跨用户查看
    admin_conv = layer.knowledge_conversations.get(
        conversation_id="c1", requesting_user_id="admin",
        requesting_role=RoleKind.ADMIN,
    )
    assert admin_conv.conversation_id == "c1"
    # 越权追加消息 → 拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_messages.append(
            message_id="mX", conversation_id="c1", role=MessageRole.USER,
            content="x", requesting_user_id="u2", requesting_role=RoleKind.DESIGNER,
        )


def test_memory_candidate_owner_isolation() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    layer.knowledge_memory_policy.propose_long_term_memory(
        candidate_id="mem1", conversation_id="c1", user_id="u1",
        content="偏好", source_references=["kb:wind-1"],
    )
    # u2 不能操作 u1 的候选
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_memory_policy.commit_long_term_memory(
            candidate_id="mem1", requesting_user_id="u2",
            actor_kind=AuditActorKind.USER,
        )
    assert layer.knowledge_memory_policy.list_for_user(user_id="u2") == []


# ---- 6. 会话审计 ----

def test_audit_conversation_message_memory_actors() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(
        conversation_id="c1", user_id="u1", title="风压", created_at="t0",
    )
    layer.knowledge_messages.append(
        message_id="m1", conversation_id="c1", role=MessageRole.USER,
        content="问", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    layer.knowledge_messages.append(
        message_id="m2", conversation_id="c1", role=MessageRole.AI,
        content="答", references=["kb:wind-1"], requesting_user_id="u1",
        requesting_role=RoleKind.DESIGNER,
    )
    layer.knowledge_memory_policy.propose_long_term_memory(
        candidate_id="mem1", conversation_id="c1", user_id="u1",
        content="偏好", source_references=["kb:wind-1"],
    )

    conv_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_CONVERSATION)
    assert len(conv_recs) >= 1
    assert conv_recs[0].actor_kind == AuditActorKind.USER

    msg_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_MESSAGE)
    assert len(msg_recs) == 2
    # 其中一条为 AI 消息（actor=AI）
    assert any(r.actor_kind == AuditActorKind.AI for r in msg_recs)
    assert any(r.actor_kind == AuditActorKind.USER for r in msg_recs)

    mem_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_MEMORY)
    assert len(mem_recs) == 1
    assert mem_recs[0].actor_kind == AuditActorKind.AI


# ---- 7. 红线总闸 ----

def test_red_line_forbidden_methods_blocked() -> None:
    layer = _layer()
    for svc in (
        layer.knowledge_conversations,
        layer.knowledge_messages,
        layer.knowledge_conversation_context,
        layer.knowledge_memory_policy,
    ):
        for forbidden in (
            "approve", "engineering_approved", "quote", "pricing",
            "sign", "authorize", "record_human_approval",
            "auto_update_knowledge", "auto_merge_knowledge",
            "auto_publish_knowledge", "auto_apply_knowledge",
            "generate_engineering_conclusion", "decide",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                _ = getattr(svc, forbidden)


def test_safety_invariants_ok_and_no_engineering_approved() -> None:
    # 红线①：工程计算处于禁用态（fail-closed 基座）。
    assert safety_invariants_ok() is True
    layer = _layer()
    # 任一服务均不得输出/持有 engineering_approved
    for svc in (
        layer.knowledge_conversations,
        layer.knowledge_messages,
        layer.knowledge_conversation_context,
        layer.knowledge_memory_policy,
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, "engineering_approved")


def test_context_visible_knowledge_filter_by_role() -> None:
    layer = _layer()
    layer.knowledge_conversations.create(conversation_id="c1", user_id="u1")
    layer.knowledge_conversation_context.update_context(
        conversation_id="c1",
        referenced_knowledge=["k-spec", "k-feedback"],
        requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    # 类型解析：k-spec→design_spec（DESIGNER 可见），k-feedback→feedback（DESIGNER 不可见）
    resolver = lambda kid: "design_spec" if kid == "k-spec" else "feedback"
    # DESIGNER 仅可见 design_spec（默认拒绝 regulation/feedback）
    visible_designer = layer.knowledge_conversation_context.filter_visible_references(
        conversation_id="c1", role=RoleKind.DESIGNER, type_resolver=resolver,
    )
    assert visible_designer == ["k-spec"]
    # ADMIN 全可见
    visible_admin = layer.knowledge_conversation_context.filter_visible_references(
        conversation_id="c1", role=RoleKind.ADMIN, type_resolver=resolver,
    )
    assert set(visible_admin) == {"k-spec", "k-feedback"}
