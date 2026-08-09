"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 知识推荐候选（任务5，Phase 3.8.9）。

新增：
- ``KnowledgeRecommendationCandidate``：AI 推荐的**知识候选**（recommendation_id / query_id /
  knowledge_id / reason / score / requires_human_review）；**仅为候选**，``requires_human_review``
  强制为 True（红线⑥：AI 不得替代人工责任）。
- ``KnowledgeRecommendationService``：组织作用域内的推荐候选服务。

红线（fail-closed，复用 3.8.0~3.8.8 基座 + 3.8.9 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **仅为候选，禁 auto_apply_knowledge**（``auto_apply_knowledge`` 被拦截，red line ③）：
  推荐项绝不自动写入/应用任何知识资产，落地须经真实人工。
- ``requires_human_review`` 强制 True（红线⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动应用知识 / 生成工程结论入口（red line ③/④/⑤）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 提议默认 AI；红线⑥：绝不伪造为人工审批）。

注意：``recommend`` 是本服务的**合法**入口（产出候选），不应列入 ``_FORBIDDEN``，否则不可达。
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
class KnowledgeRecommendationCandidate:
    """知识推荐候选（任务5）。

    **仅为候选**：``requires_human_review`` 强制 True，绝不自动应用知识（red line ③）。
    ``score`` 仅表达相关度，不代表任何工程可信结论。
    """

    recommendation_id: str
    query_id: str
    knowledge_id: str
    reason: str
    score: float = 0.0
    requires_human_review: bool = True
    created_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        # 红线⑥：推荐仅为候选，始终需要人工复核。
        self.requires_human_review = True
        if not (0.0 <= self.score <= 1.0):
            raise ValueError("score 必须在 [0,1] 区间")


class KnowledgeRecommendationService(_RedLineForbiddenMixin):
    """知识推荐候选服务（任务5）。

    提供 ``recommend`` / ``get``。推荐**仅为候选**，绝不自动应用知识或生成工程结论。

    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_apply_knowledge / generate_engineering_conclusion 等方法
    （红线②/③/④/⑥）。``recommend`` 是合法入口（产出候选），不在 forbidden 内。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识（核心：推荐仅为候选，绝不 auto_apply）
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
                "KnowledgeRecommendationService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._candidates: dict[str, KnowledgeRecommendationCandidate] = {}

    def recommend(
        self,
        *,
        recommendation_id: str,
        query_id: str,
        knowledge_id: str,
        reason: str,
        score: float = 0.0,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeRecommendationCandidate:
        """推荐一条知识候选（仅为候选，requires_human_review 强制 True，绝不自动应用知识）。

        如实记录 ``KNOWLEDGE_RETRIEVAL`` 审计（AI 提议默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推荐知识（红线①/⑤）"
            )
        cand = KnowledgeRecommendationCandidate(
            recommendation_id=recommendation_id,
            query_id=query_id,
            knowledge_id=knowledge_id,
            reason=reason,
            score=score,
            created_at=created_at,
            org_id=self._org_id,
        )
        self._candidates[recommendation_id] = cand
        if self._audit is not None:
            self._audit.record_knowledge_retrieval_action(
                record_id=f"recommend-{recommendation_id}",
                actor_id=actor_id,
                action="recommend_knowledge_candidate",
                target=recommendation_id,
                detail=(
                    f"query_id={query_id};knowledge_id={knowledge_id};"
                    f"score={cand.score};requires_human_review=true"
                ),
                ts=created_at,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return cand

    def get(self, *, recommendation_id: str) -> KnowledgeRecommendationCandidate:
        """按组织作用域读取推荐候选（跨域访问抛隔离错误）。"""
        return self._get_scoped(recommendation_id)

    def _get_scoped(self, recommendation_id: str) -> KnowledgeRecommendationCandidate:
        from agents.enterprise.organization import EnterpriseIsolationError

        c = self._candidates.get(recommendation_id)
        if c is None:
            raise EnterpriseIsolationError(f"知识推荐候选 {recommendation_id!r} 不存在")
        if c.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识推荐候选 {recommendation_id!r} 归属组织 {c.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return c


__all__ = ["KnowledgeRecommendationCandidate", "KnowledgeRecommendationService"]
