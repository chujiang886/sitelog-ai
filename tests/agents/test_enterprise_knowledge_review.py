"""Phase 3.8.10 —— 测试6：知识回答人工复核（KnowledgeAnswerReview）。

覆盖（红线⑥：真实 USER 复核，禁止 AI 代责）：
- submit_review_by_user 仅接受非空且非 ai/system 的 reviewer_user_id，决策合法 → 记录落地。
- reviewer_user_id 为 "ai" / "" → 抛红线违例（AI 不得代责）。
- 非法 decision → ValueError。
- 复核记录 requires_human_review 恒 True。
- 审计落地为 USER 动作（红线⑥：如实标注，绝不伪造为人工审批）。
- 红线②/④/⑥：本服务不持有 approve / auto_confirm / confirm / engineering_approved。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.knowledge_answer_review import (
    REVIEW_DECISION_ACCEPTED,
    REVIEW_DECISION_REJECTED,
    KnowledgeAnswerReview,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _review() -> KnowledgeAnswerReview:
    return KnowledgeAnswerReview(org_id="org-1", audit=AuditService(org_id="org-1"))


def test_submit_review_by_real_user() -> None:
    svc = _review()
    rec = svc.submit_review_by_user(
        review_id="r1", answer_id="a1", reviewer_user_id="user-expert-1",
        decision=REVIEW_DECISION_ACCEPTED, comment="来源充分，可参考",
    )
    assert rec.reviewer_user_id == "user-expert-1"
    assert rec.decision == REVIEW_DECISION_ACCEPTED
    assert rec.requires_human_review is True


def test_submit_review_rejects_ai_actor() -> None:
    svc = _review()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.submit_review_by_user(
            review_id="r2", answer_id="a2", reviewer_user_id="ai",
            decision=REVIEW_DECISION_ACCEPTED,
        )


def test_submit_review_rejects_empty_actor() -> None:
    svc = _review()
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.submit_review_by_user(
            review_id="r3", answer_id="a3", reviewer_user_id="",
            decision=REVIEW_DECISION_REJECTED,
        )


def test_submit_review_invalid_decision() -> None:
    svc = _review()
    with pytest.raises(ValueError):
        svc.submit_review_by_user(
            review_id="r4", answer_id="a4", reviewer_user_id="user-1",
            decision="not-a-decision",
        )


def test_review_audit_recorded_as_user() -> None:
    audit = AuditService(org_id="org-1")
    svc = KnowledgeAnswerReview(org_id="org-1", audit=audit)
    svc.submit_review_by_user(
        review_id="r5", answer_id="a5", reviewer_user_id="user-2",
        decision=REVIEW_DECISION_REJECTED, comment="需补充来源",
    )
    recs = audit.query(actor_kind=AuditActorKind.USER)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER


def test_review_forbids_auto_confirm() -> None:
    svc = _review()
    for name in ("auto_confirm", "confirm", "approve", "engineering_approved"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)
