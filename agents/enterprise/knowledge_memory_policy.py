"""Enterprise Knowledge Conversation & Memory Layer —— 记忆策略（任务4，Phase 3.8.11）。

新增：
- ``MemoryCandidateStatus``：记忆候选状态枚举（proposed / committed / rejected）。
- ``MemoryCandidate``：一条**长期记忆候选**（candidate_id / conversation_id / user_id /
  content / source_references / requires_human_review / status / created_at / committed_at）。
  ``requires_human_review`` 强制为 True（红线⑥）。
- ``MemoryPolicyService``：组织作用域内的记忆策略服务。

设计（红线③/④/⑥，fail-closed）：
- 记忆策略只管理「短期上下文」与「长期记忆候选」两类数据；**长期记忆候选必须经 human_review
  才能纳入**（``requires_human_review`` 强制 True）。
- AI **只能** ``propose_long_term_memory``（提议候选，默认 AI 审计）；**禁止** AI 自动保存知识
  （不持有 auto_save_knowledge / auto_update_knowledge / auto_publish_knowledge /
  auto_learn_user 等方法，红线③/④）。
- 唯一纳入长期记忆的路径是 ``commit_long_term_memory``，**必须由真实 USER 发起**
  （``require_human_actor`` 守卫，红线⑥：AI 不得代替人工责任）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）；跨域访问抛 ``EnterpriseIsolationError``。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


class MemoryCandidateStatus(str, Enum):
    """记忆候选状态（任务4）。"""

    PROPOSED = "proposed"      # AI 已提议，待人工复核
    COMMITTED = "committed"    # 经真实人工复核并纳入长期记忆
    REJECTED = "rejected"      # 经真实人工复核并拒绝


@dataclass
class MemoryCandidate:
    """长期记忆候选（任务4）。

    ``requires_human_review`` 强制为 True：候选仅作参考，纳入长期记忆须经真实人工复核
    （红线⑥）。``source_references`` 为其溯源（AI 记忆不得无来源）。
    """

    candidate_id: str
    conversation_id: str
    user_id: str
    content: str
    org_id: str = ""
    source_references: list[str] = field(default_factory=list)
    requires_human_review: bool = True
    status: MemoryCandidateStatus = MemoryCandidateStatus.PROPOSED
    created_at: str = ""
    committed_at: str = ""
    committed_by: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, MemoryCandidateStatus):
            self.status = MemoryCandidateStatus(self.status)
        # 红线⑥：长期记忆候选始终需要人工复核，AI 不得替代人工责任。
        self.requires_human_review = True


class MemoryPolicyService(_RedLineForbiddenMixin):
    """记忆策略服务（任务4）。

    提供 ``propose_long_term_memory``（AI 提议）/ ``commit_long_term_memory``（人工纳入）/
    ``reject_long_term_memory``（人工拒绝）/ ``get`` / ``list_for_user``。

    AI **只能**提议候选，绝无自动保存/写知识库路径（红线③/④）；纳入长期记忆必须经真实人工
    （``require_human_actor``，红线⑥）。跨域访问抛 ``EnterpriseIsolationError``；写路径断言
    ``safety_invariants_ok()``（红线①/⑤）。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_save_knowledge / auto_update_knowledge /
    auto_publish_knowledge / auto_learn_user 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动保存/修改/发布/合并/应用/学习知识或用户信息
        "auto_save_knowledge",
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
                "MemoryPolicyService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._candidates: dict[str, MemoryCandidate] = {}

    def propose_long_term_memory(
        self,
        *,
        candidate_id: str,
        conversation_id: str,
        user_id: str,
        content: str,
        source_references: "list[str] | None" = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> MemoryCandidate:
        """AI 提议一条长期记忆候选（默认 AI 审计；requires_human_review 强制 True，红线⑥）。

        候选仅作参考，**绝不**自动写知识库（红线③/④）。如实记录 ``KNOWLEDGE_MEMORY`` 审计。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提议记忆候选（红线①/⑤）"
            )
        cand = MemoryCandidate(
            candidate_id=candidate_id,
            conversation_id=conversation_id,
            user_id=user_id,
            content=content,
            org_id=self._org_id,
            source_references=list(source_references or []),
            status=MemoryCandidateStatus.PROPOSED,
            created_at=created_at,
        )
        self._candidates[candidate_id] = cand
        if self._audit is not None:
            self._audit.record_knowledge_memory_action(
                record_id=f"mem-{candidate_id}",
                actor_id=actor_id,
                action="propose_long_term_memory",
                target=candidate_id,
                detail=(
                    f"conversation_id={conversation_id};user_id={user_id};"
                    f"references={len(cand.source_references)};"
                    f"requires_human_review=true"
                ),
                ts=created_at,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return cand

    def _get_scoped(self, candidate_id: str) -> MemoryCandidate:
        from agents.enterprise.organization import EnterpriseIsolationError

        c = self._candidates.get(candidate_id)
        if c is None:
            raise EnterpriseIsolationError(f"记忆候选 {candidate_id!r} 不存在")
        if c.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"记忆候选 {candidate_id!r} 归属组织 {c.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return c

    def _assert_owner_or_admin(
        self, *, candidate: MemoryCandidate,
        requesting_user_id: str, requesting_role: "RoleKind | None",
    ) -> None:
        if requesting_user_id == candidate.user_id:
            return
        if requesting_role == RoleKind.ADMIN:
            return
        raise EnterpriseRedLineViolationError(
            f"用户 {requesting_user_id!r} 无权操作记忆候选 {candidate.candidate_id!r}："
            f"仅候选归属人或 ADMIN 可操作（红线⑥/任务6 访问隔离）"
        )

    def commit_long_term_memory(
        self,
        *,
        candidate_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        committed_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> MemoryCandidate:
        """将候选**纳入长期记忆**（必须由真实 USER 发起，红线⑥）。

        唯一纳入路径；``require_human_actor`` 守卫，AI 不得代责。此操作仅把经人工复核的候选
        标记为 committed（纳入本层长期记忆候选库），**绝不**自动回写知识库（红线③/④）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下纳入长期记忆（红线①/⑤）"
            )
        # 红线⑥：human-gating，必须由真实人工执行。
        require_human_actor(actor_kind or AuditActorKind.USER)
        cand = self._get_scoped(candidate_id)
        self._assert_owner_or_admin(
            candidate=cand,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        cand.status = MemoryCandidateStatus.COMMITTED
        cand.committed_at = committed_at
        cand.committed_by = actor_id or requesting_user_id
        if self._audit is not None:
            self._audit.record_knowledge_memory_action(
                record_id=f"mem-commit-{candidate_id}",
                actor_id=actor_id or requesting_user_id,
                action="commit_long_term_memory",
                target=candidate_id,
                detail=(
                    f"conversation_id={cand.conversation_id};user_id={cand.user_id};"
                    f"status=committed;requires_human_review=true"
                ),
                ts=committed_at,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return cand

    def reject_long_term_memory(
        self,
        *,
        candidate_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
        rejected_at: str = "",
        actor_id: str | None = None,
        actor_kind: "str | None" = None,
    ) -> MemoryCandidate:
        """人工拒绝候选（必须由真实 USER 发起，红线⑥）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下拒绝记忆候选（红线①/⑤）"
            )
        require_human_actor(actor_kind or AuditActorKind.USER)
        cand = self._get_scoped(candidate_id)
        self._assert_owner_or_admin(
            candidate=cand,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        cand.status = MemoryCandidateStatus.REJECTED
        if self._audit is not None:
            self._audit.record_knowledge_memory_action(
                record_id=f"mem-reject-{candidate_id}",
                actor_id=actor_id or requesting_user_id,
                action="reject_long_term_memory",
                target=candidate_id,
                detail=f"conversation_id={cand.conversation_id};status=rejected",
                ts=rejected_at,
                actor_kind=actor_kind or AuditActorKind.USER,
            )
        return cand

    def get(
        self,
        *,
        candidate_id: str,
        requesting_user_id: str,
        requesting_role: "RoleKind | None" = None,
    ) -> MemoryCandidate:
        """按组织作用域 + 访问隔离读取候选（越权抛错，任务6）。"""
        cand = self._get_scoped(candidate_id)
        self._assert_owner_or_admin(
            candidate=cand,
            requesting_user_id=requesting_user_id,
            requesting_role=requesting_role,
        )
        return cand

    def list_for_user(self, *, user_id: str) -> list[MemoryCandidate]:
        """列举某用户的全部记忆候选（组织作用域过滤；仅返回本人候选，满足访问隔离）。"""
        out: list[MemoryCandidate] = []
        for c in self._candidates.values():
            if c.org_id != self._org_id:
                continue
            if c.user_id == user_id:
                out.append(c)
        return out


__all__ = [
    "MemoryCandidateStatus",
    "MemoryCandidate",
    "MemoryPolicyService",
]
