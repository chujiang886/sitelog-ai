"""Enterprise Knowledge Agent Orchestration Layer —— 回答复核（任务6，Phase 3.8.10）。

新增：``KnowledgeAnswerReview``（人工复核门）+ ``KnowledgeAnswerReviewRecord``。

职责（红线严格限定）：
- **必须由真实人工（USER）发起复核**：``submit_review_by_user`` 强制要求 ``reviewer_user_id``
  非空且非 ``ai`` / ``system``，并断言 ``require_human_actor(USER)``（红线⑥：禁止 AI 代责）。
- **禁止 AI 自动确认 / 自动批准**：``auto_confirm`` / ``confirm`` / ``approve`` 等入口在结构上
  被 forbidden 拦截（红线②/④/⑥）。
- 复核记录只承载「人工决策（accepted / rejected / needs_revision）+ 意见」，**绝不**触发任何
  知识自动落地 / 结论自动生成 / engineering_enabled 翻转（红线③/④/⑤）。
- 可选联动 ``AuditService`` 如实标注发起方（复核动作恒为 USER，红线⑥：绝不伪造为人工审批）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)

# 合法的人工复核决策（仅描述人工意见，不承载任何批准/落地/结论语义）。
REVIEW_DECISION_ACCEPTED = "accepted"
REVIEW_DECISION_REJECTED = "rejected"
REVIEW_DECISION_NEEDS_REVISION = "needs_revision"
VALID_REVIEW_DECISIONS = frozenset(
    {
        REVIEW_DECISION_ACCEPTED,
        REVIEW_DECISION_REJECTED,
        REVIEW_DECISION_NEEDS_REVISION,
    }
)

# 视为「非真实人工」的 actor 标识（用于复核入口守卫）。
_NON_HUMAN_ACTORS = frozenset({"ai", "system", ""})


@dataclass
class KnowledgeAnswerReviewRecord:
    """知识回答人工复核记录（任务6）。

    ``requires_human_review`` 恒为 True：无论人工给出何种决策，回答采用与否仍须由真实人工
    显式闭环（红线⑥）。本记录**不**触发任何知识自动落地 / 结论自动生成。
    """

    review_id: str
    answer_id: str
    reviewer_user_id: str
    decision: str               # accepted / rejected / needs_revision
    comment: str = ""
    reviewed_at: str = ""
    org_id: str = ""
    requires_human_review: bool = True

    def __post_init__(self) -> None:
        # 红线⑥：复核记录永远需要真实人工复核闭环。
        self.requires_human_review = True


class KnowledgeAnswerReview(_RedLineForbiddenMixin):
    """知识回答人工复核（任务6）。

    真实 USER 复核门面；**禁止 AI 自动确认 / 批准**。构造/写路径断言 ``safety_invariants_ok()``
    （红线①/⑤）。

    本服务**不**持有 approve / auto_confirm / confirm / engineering_approved /
    auto_apply_knowledge / generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "auto_approve",
        "auto_confirm",
        "confirm",
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
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeAnswerReview（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._reviews: dict[str, KnowledgeAnswerReviewRecord] = {}

    def submit_review_by_user(
        self,
        *,
        review_id: str,
        answer_id: str,
        reviewer_user_id: str,
        decision: str,
        comment: str = "",
        reviewed_at: str = "",
    ) -> KnowledgeAnswerReviewRecord:
        """真实 USER 提交复核决策（红线⑥：必须由真实人工发起，AI 不得代责）。

        - ``reviewer_user_id`` 必须非空且非 ``ai`` / ``system``（否则抛红线违例）。
        - 强制 ``require_human_actor(USER)`` 结构性断言。
        - ``decision`` 必须在 ``VALID_REVIEW_DECISIONS`` 内。
        复核记录仅承载人工意见，**绝不**触发知识自动落地 / 结论自动生成（红线③/④/⑤）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交复核（红线①/⑤）"
            )
        if not reviewer_user_id or reviewer_user_id in _NON_HUMAN_ACTORS:
            raise EnterpriseRedLineViolationError(
                "红线⑥：知识回答复核必须由真实人工（USER）发起，"
                "reviewer_user_id 必须非空且非 ai/system；AI 不得代替人工责任"
            )
        # 结构性断言：复核动作的真实发起方必须是 USER（红线⑥）。
        require_human_actor(AuditActorKind.USER)
        if decision not in VALID_REVIEW_DECISIONS:
            raise ValueError(
                f"非法复核决策 {decision!r}：必须为 accepted / rejected / needs_revision"
            )
        record = KnowledgeAnswerReviewRecord(
            review_id=review_id,
            answer_id=answer_id,
            reviewer_user_id=reviewer_user_id,
            decision=decision,
            comment=comment,
            reviewed_at=reviewed_at,
            org_id=self._org_id,
        )
        self._reviews[review_id] = record
        if self._audit is not None:
            # 复核动作由真实人工发起，actor_kind 恒为 USER（红线⑥：如实标注，绝不伪造）。
            self._audit.record_user_action(
                record_id=f"review-{review_id}",
                actor_id=reviewer_user_id,
                action=f"submit_knowledge_answer_review:{decision}",
                target=answer_id,
                detail=comment,
                ts=reviewed_at,
            )
        return record

    def get(self, *, review_id: str) -> KnowledgeAnswerReviewRecord:
        """按组织作用域读取复核记录（跨域访问抛隔离错误）。"""
        from agents.enterprise.organization import EnterpriseIsolationError

        r = self._reviews.get(review_id)
        if r is None:
            raise EnterpriseIsolationError(f"复核记录 {review_id!r} 不存在")
        if r.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"复核记录 {review_id!r} 归属组织 {r.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return r


__all__ = [
    "KnowledgeAnswerReview",
    "KnowledgeAnswerReviewRecord",
    "REVIEW_DECISION_ACCEPTED",
    "REVIEW_DECISION_REJECTED",
    "REVIEW_DECISION_NEEDS_REVISION",
    "VALID_REVIEW_DECISIONS",
]
