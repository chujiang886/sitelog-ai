"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试3：知识更新候选（任务3，Phase 3.8.7）。

覆盖（KnowledgeUpdateCandidateService）：
- KnowledgeUpdateCandidate / KnowledgeChangeType 建模（add / update / delete / correct / clarify）。
- propose_candidate 只提候选，**绝不**自动写入知识库（red line ③）。requires_human_review 恒 True。
- get / list_candidates 按 source / requires_human_review 过滤；跨域隔离。
- 不持有 apply / merge / approve / auto_update_knowledge 等 forbidden 方法（红线③核心拦截）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.knowledge_candidate import (
    KnowledgeChangeType,
    KnowledgeUpdateCandidate,
    KnowledgeUpdateCandidateService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeUpdateCandidateService:
    return KnowledgeUpdateCandidateService(
        org_id=org_id, audit=AuditService(org_id=org_id)
    )


def test_change_type_enum() -> None:
    for name, v in (
        ("ADD", "add"),
        ("UPDATE", "update"),
        ("DELETE", "delete"),
        ("CORRECT", "correct"),
        ("CLARIFY", "clarify"),
    ):
        assert getattr(KnowledgeChangeType, name).value == v


def test_propose_candidate_requires_human_review_forced() -> None:
    svc = _svc()
    cand = svc.propose_candidate(
        candidate_id="c1",
        source="feedback-f1",
        change_type=KnowledgeChangeType.ADD,
        content="新增：导出功能说明",
        evidence="feedback-f1",
    )
    assert isinstance(cand, KnowledgeUpdateCandidate)
    # 红线③/⑥：候选恒需人工复核，AI 不得绕过
    assert cand.requires_human_review is True


def test_propose_does_not_write_repo() -> None:
    # 红线③核心：候选服务只登记候选，绝不落地知识库。
    svc = _svc()
    svc.propose_candidate(
        candidate_id="c1", source="manual", change_type=KnowledgeChangeType.UPDATE,
        content="x", evidence="y",
    )
    # 不存在 apply / merge / commit / write 等落地方法
    for name in ("apply", "merge", "commit", "write", "approve"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)
    # 审计如实记录候选（AI 提议默认 AI）
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_CANDIDATE)
    assert len(recs) == 1 and recs[0].actor_kind == AuditActorKind.AI


def test_list_candidates_filters() -> None:
    svc = _svc()
    svc.propose_candidate(
        candidate_id="c1", source="feedback-f1", change_type=KnowledgeChangeType.ADD,
        content="x", evidence="y",
    )
    svc.propose_candidate(
        candidate_id="c2", source="validation-v1", change_type=KnowledgeChangeType.CORRECT,
        content="z", evidence="w",
    )
    assert len(svc.list_candidates(source="feedback-f1")) == 1
    assert len(svc.list_candidates(requires_human_review=True)) == 2
    assert svc.get(candidate_id="c2").change_type == KnowledgeChangeType.CORRECT


def test_forbidden_auto_update_knowledge_methods() -> None:
    svc = _svc()
    for name in (
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "engineering_approved",
        "record_human_approval",
        "recommend",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.propose_candidate(
        candidate_id="c1", source="manual", change_type=KnowledgeChangeType.ADD,
        content="x", evidence="y",
    )
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(candidate_id="c1")
