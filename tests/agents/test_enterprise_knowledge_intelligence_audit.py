"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试7：审计增强（任务7，Phase 3.8.9/3.8.11）。

覆盖（AuditActionCategory / AuditService）：
- 新增 3 个审计类别（KNOWLEDGE_SEARCH / KNOWLEDGE_RETRIEVAL / KNOWLEDGE_QUERY）。
- record_knowledge_search_action / record_knowledge_retrieval_action / record_knowledge_query_action
  如实记录，actor 真实（search/retrieval 默认 USER，query 默认 AI）。
- 红线⑥：访问 record_human_approval 被拦截（绝不伪造人工审批）。
- 审计类别累计正确（3.8.8 的 16 个 + 3.8.9 的 3 个 + 3.8.10 的 4 个 + 3.8.11 的 3 个
  + 3.8.12 的 3 个 = 29）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def test_three_new_categories_exist() -> None:
    assert AuditActionCategory.KNOWLEDGE_SEARCH.value == "knowledge_search"
    assert AuditActionCategory.KNOWLEDGE_RETRIEVAL.value == "knowledge_retrieval"
    assert AuditActionCategory.KNOWLEDGE_QUERY.value == "knowledge_query"


def test_knowledge_intelligence_categories_registered() -> None:
    """本层只对**自己新增的 3 类**已在全局枚举注册负责。

    Phase 3.8.31 Task 9：原函数名停留在 ``_44``、注释推导链停留在 56，而实际
    断言值已被历次阶段改到 72 —— 名称、注释、断言三者互相脱节，是典型的脆性
    契约。审计大类**总数**的唯一权威断言保留在
    ``tests/agents/test_enterprise_knowledge_governance_audit.py``
    （``EXPECTED_CATEGORIES`` 全量成员名集合 + 总数）。
    """
    names = set(AuditActionCategory.__members__)
    assert {
        "KNOWLEDGE_SEARCH",
        "KNOWLEDGE_RETRIEVAL",
        "KNOWLEDGE_QUERY",
    } <= names


def test_record_knowledge_search_action() -> None:
    a = _audit()
    a.record_knowledge_search_action(
        record_id="s1", actor_id="u1", action="create_knowledge_search",
        target="q1", detail="user_id=u1",
    )
    recs = a.query(category=AuditActionCategory.KNOWLEDGE_SEARCH)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER


def test_record_knowledge_retrieval_action() -> None:
    a = _audit()
    a.record_knowledge_retrieval_action(
        record_id="r1", actor_id="u1", action="retrieve_knowledge_candidates",
        target="开窗面积", detail="returned=3",
    )
    recs = a.query(category=AuditActionCategory.KNOWLEDGE_RETRIEVAL)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER


def test_record_knowledge_query_action_default_ai() -> None:
    a = _audit()
    a.record_knowledge_query_action(
        record_id="q1", actor_id="ai", action="draft_knowledge_answer",
        target="a1", detail="references=2",
    )
    recs = a.query(category=AuditActionCategory.KNOWLEDGE_QUERY)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_audit_no_record_human_approval() -> None:
    a = _audit()
    # 红线⑥：访问即抛，绝不伪造人工审批
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = a.record_human_approval  # type: ignore[attr-defined]
