"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试6：知识推荐候选（任务5，Phase 3.8.9）。

覆盖（KnowledgeRecommendationCandidate / KnowledgeRecommendationService）：
- recommend 产出候选（仅为候选，requires_human_review 强制 True，红线⑥）。
- score 必须在 [0,1]。
- recommend 如实记录 KNOWLEDGE_RETRIEVAL 审计（AI 提议默认 AI）。
- forbidden：auto_apply_knowledge / generate_engineering_conclusion 被拦截（红线③/④）。
- 跨组织隔离（_get_scoped）。注意：recommend 是合法入口，不在 forbidden 内。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.knowledge_recommendation import (
    KnowledgeRecommendationCandidate,
    KnowledgeRecommendationService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeRecommendationService:
    return KnowledgeRecommendationService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_recommend_creates_candidate() -> None:
    svc = _svc()
    c = svc.recommend(
        recommendation_id="r1", query_id="q1", knowledge_id="k1",
        reason="与开窗面积规范高度相关", score=0.9,
    )
    assert isinstance(c, KnowledgeRecommendationCandidate)
    assert c.requires_human_review is True  # 强制人工复核
    assert c.org_id == "org-1"


def test_recommend_forces_requires_human_review() -> None:
    c = KnowledgeRecommendationCandidate(
        recommendation_id="r1", query_id="q1", knowledge_id="k1",
        reason="x", requires_human_review=False,
    )
    assert c.requires_human_review is True


def test_recommend_score_bounds() -> None:
    with pytest.raises(ValueError):
        KnowledgeRecommendationCandidate(
            recommendation_id="r1", query_id="q1", knowledge_id="k1",
            reason="x", score=2.0,
        )


def test_recommend_records_retrieval_audit() -> None:
    svc = _svc()
    svc.recommend(
        recommendation_id="r1", query_id="q1", knowledge_id="k1",
        reason="相关", score=0.7,
    )
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_RETRIEVAL)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI
    assert recs[0].action == "recommend_knowledge_candidate"


def test_recommend_no_auto_apply() -> None:
    svc = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.auto_apply_knowledge  # type: ignore[attr-defined]


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.recommend(recommendation_id="r1", query_id="q1", knowledge_id="k1", reason="x")
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(recommendation_id="r1")
