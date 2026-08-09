"""Enterprise Knowledge Governance & Version Control Layer —— 知识变更审核（任务3，Phase 3.8.8）。

新增：
- ``ReviewResult``：审核结果（accepted / rejected / needs_revision）。
- ``KnowledgeChangeReview``：知识变更审核（review_id / candidate_id / reviewer /
  result / comment / timestamp）；reviewer 必须 USER。
- ``KnowledgeChangeReviewService``：仅**记录**人工审核结论；**禁止** AI 自动审核（需
  ``require_human_actor`` USER，红线⑥）。

红线（fail-closed，复用 3.8.0~3.8.7 基座 + 3.8.8 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **create_review 必须由真实 USER 执行**（``require_human_actor``，红线⑥）：AI 不得自动审核
  任何知识变更（禁 AI 自动 approve，任务3 明确要求 reviewer 必须 USER）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动批准入口（``auto_update_knowledge`` / ``auto_merge_knowledge`` /
  ``auto_approve_knowledge``，红线③/⑤）。
- 本服务**不**承载任何经营决策/审批/管理建议入口（红线④/⑤）。
- 可选联动 ``AuditService.record_knowledge_review_action`` 如实标注发起方 actor
  （审核节点强制 USER，红线⑥）。

代码库无 KnowledgeRepository：本服务仅记录「人工审核结论」这一事实，**绝不**将审核结论自动
落地为知识资产改动（red line ③），实际改动须由真实人工在知识库侧执行。
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
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


class ReviewResult(str, Enum):
    """知识变更审核结果（任务3）。

    仅描述人工审核结论，不承载任何自动落地语义；实际知识改动须经人工在知识库侧执行（红线③）。
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


@dataclass
class KnowledgeChangeReview:
    """知识变更审核（任务3）。

    仅记录「人工对某候选的审核结论」；``reviewer`` 必须 USER（由服务层强制 ``require_human_actor``，
    AI 不得代行，红线⑥）。``org_id`` 为 Enterprise 层统一组织隔离字段。
    """

    review_id: str
    candidate_id: str
    reviewer: str                      # 审核人（必须 USER actor_id）
    result: ReviewResult
    comment: str = ""
    timestamp: str = ""
    org_id: str = ""                   # 归属组织（隔离作用域）

    def __post_init__(self) -> None:
        if not isinstance(self.result, ReviewResult):
            self.result = ReviewResult(self.result)


class KnowledgeChangeReviewService(_RedLineForbiddenMixin):
    """知识变更审核服务（任务3）。

    仅记录人工审核结论；跨域访问抛 ``EnterpriseIsolationError``；写路径断言
    ``safety_invariants_ok()``（红线①/⑤）。**create_review 必须由真实 USER 执行**
    （``require_human_actor``，红线⑥）：AI 不得自动审核。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize
    / record_human_approval / auto_update_knowledge / auto_merge_knowledge /
    auto_approve_knowledge 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动改/合并/批准知识（核心：审核只记录结论，绝不落地）
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "apply",
        "merge",
        "commit",
        "write",
        # 红线④/⑤：禁止自动经营决策 / 审批 / 管理建议
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "AnalyticsVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeChangeReviewService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._reviews: dict[str, KnowledgeChangeReview] = {}

    def create_review(
        self,
        *,
        review_id: str,
        candidate_id: str,
        reviewer: str,
        result: ReviewResult,
        comment: str = "",
        timestamp: str = "",
        actor_kind: Any,
    ) -> KnowledgeChangeReview:
        """记录一条人工审核结论 —— **必须由真实 USER 执行**（红线⑥）。

        AI 不得自动审核（``require_human_actor`` 守卫）；``result`` 为人工给出的结论
        （accepted / rejected / needs_revision）。审核仅记录事实，绝不自动落地知识改动（红线③）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录知识审核（红线①/⑤）"
            )
        # 红线⑥：审核是人工责任节点，必须由真实人工发起。
        require_human_actor(actor_kind)
        rev = KnowledgeChangeReview(
            review_id=review_id,
            candidate_id=candidate_id,
            reviewer=reviewer,
            result=result,
            comment=comment,
            timestamp=timestamp,
            org_id=self._org_id,
        )
        self._reviews[review_id] = rev
        if self._audit is not None:
            self._audit.record_knowledge_review_action(
                record_id=f"review-{review_id}",
                actor_id=reviewer,
                action="create_knowledge_review",
                target=candidate_id,
                detail=(
                    f"review_id={review_id};result={result.value};"
                    f"comment={comment}"
                ),
                ts=timestamp,
                actor_kind=AuditActorKind.USER,
            )
        return rev

    def get(self, *, review_id: str) -> KnowledgeChangeReview:
        """按组织作用域读取审核（跨域访问抛隔离错误）。"""
        return self._get_scoped(review_id)

    def list_reviews(
        self,
        *,
        candidate_id: str = "",
        result: "ReviewResult | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[KnowledgeChangeReview]:
        """列出当前组织下审核（可按 candidate_id / result 过滤）。"""
        out = [r for r in self._reviews.values() if r.org_id == self._org_id]
        if candidate_id:
            out = [r for r in out if r.candidate_id == candidate_id]
        if result is not None:
            out = [r for r in out if r.result == result]
        return out

    def _get_scoped(self, review_id: str) -> KnowledgeChangeReview:
        from agents.enterprise.organization import EnterpriseIsolationError

        rev = self._reviews.get(review_id)
        if rev is None:
            raise EnterpriseIsolationError(f"知识变更审核 {review_id!r} 不存在")
        if rev.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识变更审核 {review_id!r} 归属组织 {rev.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return rev


__all__ = [
    "ReviewResult",
    "KnowledgeChangeReview",
    "KnowledgeChangeReviewService",
]
