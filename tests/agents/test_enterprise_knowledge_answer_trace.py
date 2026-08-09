"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试5：回答草稿须引用来源（任务4，Phase 3.8.9）。

覆盖（KnowledgeAnswerDraft / KnowledgeAnswerService）：
- 回答草稿必须引用来源（references 非空），空 references 抛 ValueError（禁无来源回答）。
- requires_human_review 强制 True（红线⑥：AI 不得替代人工责任）。
- confidence 必须在 [0,1]。
- draft_answer 如实记录 KNOWLEDGE_QUERY 审计（AI 起草默认 AI）。
- forbidden：auto_apply_knowledge / generate_engineering_conclusion 被拦截（红线③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.knowledge_answer import (
    KnowledgeAnswerDraft,
    KnowledgeAnswerService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeAnswerService:
    return KnowledgeAnswerService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_draft_requires_references() -> None:
    with pytest.raises(ValueError):
        KnowledgeAnswerDraft(answer_id="a1", query_id="q1", references=[])


def test_draft_forces_requires_human_review() -> None:
    d = KnowledgeAnswerDraft(
        answer_id="a1", query_id="q1", references=["k1"],
        requires_human_review=False,  # 试图关闭
    )
    # 红线⑥：构造后被强制拉回 True
    assert d.requires_human_review is True


def test_draft_confidence_bounds() -> None:
    with pytest.raises(ValueError):
        KnowledgeAnswerDraft(
            answer_id="a1", query_id="q1", references=["k1"], confidence=1.5,
        )


def test_draft_answer_records_query_audit() -> None:
    svc = _svc()
    d = svc.draft_answer(
        answer_id="a1", query_id="q1", references=["k1", "k2"],
        content="按规范开窗面积不小于...", confidence=0.8,
    )
    assert d.requires_human_review is True
    assert d.org_id == "org-1"
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_QUERY)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI
    assert "references=2" in recs[0].detail


def test_draft_no_source_less_answer_rejected() -> None:
    svc = _svc()
    with pytest.raises(ValueError):
        svc.draft_answer(answer_id="a1", query_id="q1", references=[])


def test_forbidden_auto_apply_and_conclusion() -> None:
    svc = _svc()
    for name in ("auto_apply_knowledge", "generate_engineering_conclusion", "auto_update_knowledge"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)
