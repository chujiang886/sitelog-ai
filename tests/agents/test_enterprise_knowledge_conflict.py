"""Enterprise Knowledge Governance & Version Control Layer —— 测试4：知识版本冲突（任务4，Phase 3.8.8）。

覆盖（KnowledgeConflictCandidate / KnowledgeConflictService）：
- KnowledgeConflictCandidate（conflict_id / knowledge_a / knowledge_b / reason / evidence /
  requires_human_review）；requires_human_review 恒 True（冲突解决须人工，红线③/⑥）。
- discover_conflict **只发现冲突**，**绝不**自动 merge（red line ③）：登记事实 + 审计
  （KNOWLEDGE_CONFLICT，默认 AI）。
- list_conflicts 按涉及 knowledge_id / requires_human_review 过滤；跨组织隔离。
- forbidden 方法拦截（auto_merge_knowledge / merge / apply / commit / write 等核心禁 merge）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.knowledge_conflict import (
    KnowledgeConflictCandidate,
    KnowledgeConflictService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeConflictService:
    return KnowledgeConflictService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_conflict_candidate_forces_requires_human_review() -> None:
    c = KnowledgeConflictCandidate(
        conflict_id="cf1", knowledge_a="k1", knowledge_b="k2",
        reason="矛盾结论", evidence="v1-hash!=v2-hash",
        requires_human_review=False,  # 试图绕过
    )
    # 红线③/⑥：__post_init__ 强制 requires_human_review=True
    assert c.requires_human_review is True
    assert c.org_id == ""


def test_discover_conflict_only_registers() -> None:
    svc = _svc()
    c = svc.discover_conflict(
        conflict_id="cf1", knowledge_a="k1", knowledge_b="k2",
        reason="矛盾结论", evidence="v1!=v2",
    )
    assert isinstance(c, KnowledgeConflictCandidate)
    assert c.requires_human_review is True
    assert c.org_id == "org-1"
    # 审计如实记录（AI 发现默认 AI）
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_CONFLICT)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI
    assert recs[0].action == "discover_knowledge_conflict"


def test_discover_conflict_does_not_merge() -> None:
    # 红线③核心：冲突服务只发现，绝不自动 merge。
    svc = _svc()
    svc.discover_conflict(
        conflict_id="cf1", knowledge_a="k1", knowledge_b="k2",
        reason="x", evidence="y",
    )
    for name in ("auto_merge_knowledge", "merge", "apply", "commit", "write"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_list_conflicts_filters() -> None:
    svc = _svc()
    svc.discover_conflict(
        conflict_id="cf1", knowledge_a="k1", knowledge_b="k2", reason="x", evidence="y"
    )
    svc.discover_conflict(
        conflict_id="cf2", knowledge_a="k3", knowledge_b="k4", reason="z", evidence="w"
    )
    # 按涉及 knowledge_id 过滤（a 或 b 命中）
    assert len(svc.list_conflicts(knowledge_id="k1")) == 1
    assert len(svc.list_conflicts(knowledge_id="k2")) == 1
    assert len(svc.list_conflicts(knowledge_id="k9")) == 0
    # 全部 requires_human_review=True
    assert len(svc.list_conflicts(requires_human_review=True)) == 2
    assert svc.get(conflict_id="cf1").knowledge_a == "k1"


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
    svc_a.discover_conflict(
        conflict_id="cf1", knowledge_a="k1", knowledge_b="k2", reason="x", evidence="y"
    )
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(conflict_id="cf1")
