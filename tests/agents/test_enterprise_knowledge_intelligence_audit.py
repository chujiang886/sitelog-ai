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


def test_total_audit_categories_44() -> None:
    # 3.8.8 收口 16 个 + 3.8.9 新增 3 个 + 3.8.10 新增 4 个 + 3.8.11 新增 3 个
    # + 3.8.12 新增 3 个 + 3.8.13 新增 3 个（agent_register/agent_execution/
    # agent_version）+ 3.8.14 新增 3 个（agent_metric/agent_trace/
    # agent_health）+ 3.8.15 新增 3 个（agent_quality/agent_evaluation/
    # agent_feedback）+ 3.8.16 新增 3 个（agent_resource/agent_cost/
    # agent_cost_report）+ 3.8.17 新增 3 个（agent_policy/agent_runtime_check/
    # agent_tool_access）+ 3.8.18 新增 3 个（agent_security_event/agent_risk/
    # agent_risk_review）+ 3.8.19 新增 3 个（agent_compliance_rule/
    # agent_compliance_check/agent_compliance_risk）+ 3.8.20 新增 3 个
    # （agent_governance_dashboard/agent_governance_report/
    #  agent_governance_insight）= 53；3.8.21 新增 3 个
    # （agent_governance_task/agent_governance_action/
    #  agent_governance_closure）= 56
    assert len(list(AuditActionCategory)) == 68


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
