"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 知识回答草稿（任务4，Phase 3.8.9）。

新增：
- ``KnowledgeAnswerDraft``：AI 起草的**回答草稿**（answer_id / query_id / references /
  confidence / requires_human_review）；**必须引用来源**（references 非空，禁无来源回答），
  ``requires_human_review`` 强制为 True（红线⑥：AI 不得替代人工责任）。
- ``KnowledgeAnswerService``：组织作用域内的回答草稿服务。

红线（fail-closed，复用 3.8.0~3.8.8 基座 + 3.8.9 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 回答草稿**必须引用来源**（references 非空），禁止无来源回答（任务4 核心要求）。
- ``requires_human_review`` 强制 True：草稿仅作参考，最终采用须经真实人工（红线⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动应用知识 / 生成工程结论入口（``auto_apply_knowledge`` /
  ``generate_engineering_conclusion`` 等，红线③/④/⑤）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 起草默认 AI；红线⑥：绝不伪造为人工审批）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class KnowledgeAnswerDraft:
    """知识回答草稿（任务4）。

    **必须引用来源**（``references`` 非空），禁止无来源回答；``requires_human_review`` 强制为
    True（AI 起草仅作参考，最终采用须经真实人工，红线⑥）。``confidence`` 仅表达草稿自身置信度，
    不代表任何工程结论可信度。
    """

    answer_id: str
    query_id: str
    references: list[str]            # 引用的知识来源（非空，禁无来源回答）
    confidence: float = 0.0          # 草稿自身置信度（[0,1]）
    requires_human_review: bool = True
    content: str = ""
    created_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        # 任务4 核心：禁止无来源回答。
        if not self.references:
            raise ValueError(
                "KnowledgeAnswerDraft 必须引用来源（references 非空）：禁止无来源回答"
            )
        # 红线⑥：草稿始终需要人工复核，AI 不得替代人工责任。
        self.requires_human_review = True
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence 必须在 [0,1] 区间")


class KnowledgeAnswerService(_RedLineForbiddenMixin):
    """知识回答草稿服务（任务4）。

    提供 ``draft_answer`` / ``get``。草稿**仅候选**，绝不自动应用知识或生成工程结论。

    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_apply_knowledge / generate_engineering_conclusion 等方法
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
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
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
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeAnswerService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._drafts: dict[str, KnowledgeAnswerDraft] = {}

    def draft_answer(
        self,
        *,
        answer_id: str,
        query_id: str,
        references: list[str],
        content: str = "",
        confidence: float = 0.0,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeAnswerDraft:
        """起草一份**带来源引用**的回答草稿（references 非空，requires_human_review 强制 True）。

        草稿仅候选，绝不自动应用知识或生成工程结论（red line ③/④）。如实记录
        ``KNOWLEDGE_QUERY`` 审计（AI 起草默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下起草回答（红线①/⑤）"
            )
        draft = KnowledgeAnswerDraft(
            answer_id=answer_id,
            query_id=query_id,
            references=list(references),
            confidence=confidence,
            content=content,
            created_at=created_at,
            org_id=self._org_id,
        )
        self._drafts[answer_id] = draft
        if self._audit is not None:
            self._audit.record_knowledge_query_action(
                record_id=f"answer-{answer_id}",
                actor_id=actor_id,
                action="draft_knowledge_answer",
                target=answer_id,
                detail=(
                    f"query_id={query_id};references={len(draft.references)};"
                    f"confidence={draft.confidence};requires_human_review=true"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return draft

    def get(self, *, answer_id: str) -> KnowledgeAnswerDraft:
        """按组织作用域读取草稿（跨域访问抛隔离错误）。"""
        return self._get_scoped(answer_id)

    def _get_scoped(self, answer_id: str) -> KnowledgeAnswerDraft:
        from agents.enterprise.organization import EnterpriseIsolationError

        d = self._drafts.get(answer_id)
        if d is None:
            raise EnterpriseIsolationError(f"回答草稿 {answer_id!r} 不存在")
        if d.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"回答草稿 {answer_id!r} 归属组织 {d.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return d


__all__ = ["KnowledgeAnswerDraft", "KnowledgeAnswerService"]
