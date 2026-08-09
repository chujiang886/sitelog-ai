"""Enterprise Knowledge Governance & Version Control Layer —— 测试3：知识变更审核（任务3，Phase 3.8.8）。

覆盖（KnowledgeChangeReview / KnowledgeChangeReviewService）：
- ReviewResult 建模（accepted / rejected / needs_revision）。
- KnowledgeChangeReview 数据类（review_id / candidate_id / reviewer / result / comment /
  timestamp / org_id）；__post_init__ 强制枚举。
- create_review **必须由真实 USER 执行**（require_human_actor，红线⑥）：AI 不得自动审核
  （禁 AI 自动 approve，任务3 明确要求 reviewer 必须 USER）。
- 审核只记录结论，绝不自动落地知识改动（红线③）。
- list_reviews 按 candidate_id / result 过滤；跨组织隔离；forbidden 方法拦截。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.knowledge_change_review import (
    ReviewResult,
    KnowledgeChangeReview,
    KnowledgeChangeReviewService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeChangeReviewService:
    return KnowledgeChangeReviewService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_review_result_enum() -> None:
    for name, v in (
        ("ACCEPTED", "accepted"),
        ("REJECTED", "rejected"),
        ("NEEDS_REVISION", "needs_revision"),
    ):
        assert getattr(ReviewResult, name).value == v


def test_change_review_post_init_normalizes_result() -> None:
    r = KnowledgeChangeReview(
        review_id="r1", candidate_id="c1", reviewer="u", result="accepted"
    )
    assert r.result is ReviewResult.ACCEPTED
    assert r.org_id == ""


def test_create_review_requires_user_actor() -> None:
    svc = _svc()
    # 红线⑥：AI 不得自动审核
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_review(
            review_id="r1", candidate_id="c1", reviewer="ai-1",
            result=ReviewResult.ACCEPTED, actor_kind=AuditActorKind.AI,
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_review(
            review_id="r1", candidate_id="c1", reviewer="x",
            result=ReviewResult.ACCEPTED, actor_kind=None,
        )


def test_create_review_by_user_succeeds() -> None:
    svc = _svc()
    rev = svc.create_review(
        review_id="r1", candidate_id="c1", reviewer="user-1",
        result=ReviewResult.ACCEPTED, comment="lgtm",
        actor_kind=AuditActorKind.USER,
    )
    assert isinstance(rev, KnowledgeChangeReview)
    assert rev.reviewer == "user-1"
    assert rev.result is ReviewResult.ACCEPTED
    assert rev.org_id == "org-1"
    # 审计节点 actor_kind 强制 USER（KNOWLEDGE_REVIEW 分类）
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_REVIEW)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER
    assert recs[0].action == "create_knowledge_review"


def test_create_review_results_variants() -> None:
    svc = _svc()
    for rid, res in (
        ("r1", ReviewResult.REJECTED),
        ("r2", ReviewResult.NEEDS_REVISION),
        ("r3", ReviewResult.ACCEPTED),
    ):
        svc.create_review(
            review_id=rid, candidate_id="c1", reviewer="user-1",
            result=res, actor_kind=AuditActorKind.USER,
        )
    assert len(svc.list_reviews(candidate_id="c1")) == 3
    assert len(svc.list_reviews(result=ReviewResult.REJECTED)) == 1
    assert len(svc.list_reviews(result=ReviewResult.NEEDS_REVISION)) == 1


def test_create_review_does_not_write_knowledge() -> None:
    # 红线③：审核只记录结论，绝不落地知识改动；不存在 apply/merge/approve 等落地方法。
    svc = _svc()
    svc.create_review(
        review_id="r1", candidate_id="c1", reviewer="user-1",
        result=ReviewResult.ACCEPTED, actor_kind=AuditActorKind.USER,
    )
    for name in ("apply", "merge", "commit", "write", "approve"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_forbidden_auto_knowledge_and_decision_methods() -> None:
    svc = _svc()
    for name in (
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "recommend",
        "decide",
        "auto_decision",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.create_review(
        review_id="r1", candidate_id="c1", reviewer="user-1",
        result=ReviewResult.ACCEPTED, actor_kind=AuditActorKind.USER,
    )
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(review_id="r1")
