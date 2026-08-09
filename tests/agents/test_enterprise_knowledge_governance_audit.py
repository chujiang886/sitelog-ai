"""Enterprise Knowledge Governance & Version Control Layer —— 测试5：审计增强（Phase 3.8.8）。

    覆盖（audit.py）：
- AuditActionCategory 共 29 个枚举值（3.8.8 的 KNOWLEDGE_VERSION / KNOWLEDGE_REVIEW /
  KNOWLEDGE_CONFLICT；3.8.9 的 KNOWLEDGE_SEARCH / KNOWLEDGE_RETRIEVAL / KNOWLEDGE_QUERY；
  3.8.10 的 KNOWLEDGE_AGENT_QUERY / KNOWLEDGE_AGENT_RETRIEVE /
  KNOWLEDGE_AGENT_VALIDATE / KNOWLEDGE_AGENT_DRAFT；
  3.8.11 的 KNOWLEDGE_CONVERSATION / KNOWLEDGE_MESSAGE / KNOWLEDGE_MEMORY；
  3.8.12 的 KNOWLEDGE_TASK / KNOWLEDGE_SUBTASK / KNOWLEDGE_AGENT_WORKFLOW）。
- AuditService 新增 record_knowledge_version_action / record_knowledge_review_action /
  record_knowledge_conflict_action，分类落地正确，actor 真实（默认 AI，人工节点显式 USER）。
- Phase 3.8.10：新增 record_knowledge_agent_*_action 四个智能体审计方法。
- Phase 3.8.11：新增 record_knowledge_conversation_action / record_knowledge_message_action /
  record_knowledge_memory_action 三个会话/记忆审计方法。
- Phase 3.8.12：新增 record_knowledge_task_action / record_knowledge_subtask_action /
  record_knowledge_agent_workflow_action 三个任务规划/子任务/工作流审计方法。
- require_human_actor 守卫：actor_kind != USER 抛 EnterpriseRedLineViolationError（红线⑥）。
- 无 record_human_approval（红线⑥：不提供「代记人工批准」入口）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


EXPECTED_CATEGORIES = {
    "ai_action", "user_action", "workflow_event", "permission", "collaboration",
    "dashboard", "data_insight", "trend_analysis", "anomaly_detection",
    "report_generation", "feedback", "knowledge_candidate", "validation",
    "knowledge_version", "knowledge_review", "knowledge_conflict",
    "knowledge_search", "knowledge_retrieval", "knowledge_query",
    "knowledge_agent_query", "knowledge_agent_retrieve",
    "knowledge_agent_validate", "knowledge_agent_draft",
    "knowledge_conversation", "knowledge_message", "knowledge_memory",
    "knowledge_task", "knowledge_subtask", "knowledge_agent_workflow",
    "agent_register", "agent_execution", "agent_version",
    "agent_metric", "agent_trace", "agent_health",
    "agent_quality", "agent_evaluation", "agent_feedback",
    "agent_resource", "agent_cost", "agent_cost_report",
    "agent_policy", "agent_runtime_check", "agent_tool_access",
    # Phase 3.8.18：企业智能体安全与风险治理层（+3）
    "agent_security_event", "agent_risk", "agent_risk_review",
    # Phase 3.8.19：企业智能体合规与审计智能层（+3）
    "agent_compliance_rule", "agent_compliance_check", "agent_compliance_risk",
    # Phase 3.8.20：企业智能体治理智能中枢层（+3）
    "agent_governance_dashboard", "agent_governance_report", "agent_governance_insight",
    # Phase 3.8.21：企业智能体治理流程与责任闭环层（+3）
    "agent_governance_task", "agent_governance_action", "agent_governance_closure",
    # Phase 3.8.22：企业智能体治理知识与持续改进层（+3）
    "agent_governance_case", "agent_governance_knowledge", "agent_governance_improvement",
    # Phase 3.8.23：企业智能体治理知识检索与辅助学习层（+3）
    "agent_governance_knowledge_query", "agent_governance_knowledge_retrieval",
    "agent_governance_assistance",
    # Phase 3.8.24：企业智能体治理知识助手层（+3）
    "agent_governance_assistant_query", "agent_governance_assistant_context",
    "agent_governance_assistant_draft",
    # Phase 3.8.25：企业智能体治理工作流编排层（+3）
    "agent_governance_workflow_create", "agent_governance_workflow_review",
    "agent_governance_workflow_execution",
}


def test_audit_action_category_has_knowledge_members() -> None:
    members = {c.value for c in AuditActionCategory}
    assert members == EXPECTED_CATEGORIES
    assert len(members) == 68
    # 程序化校验：枚举每个成员名均存在（规避手写元组形近污染，3.8.11 教训）。
    for name in AuditActionCategory.__members__:
        assert hasattr(AuditActionCategory, name)


def test_record_knowledge_version_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_version_action(
        record_id="version-v1", actor_id="ai-1",
        action="create_knowledge_version", target="v1",
        detail="knowledge_id=k1", ts="2026-08-04T00:00:00Z",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_VERSION)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_VERSION
    # 缺省 actor_kind → AI
    assert recs[0].actor_kind == AuditActorKind.AI


def test_record_knowledge_review_action_user_actor() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_review_action(
        record_id="review-r1", actor_id="user-1",
        action="create_knowledge_review", target="c1",
        detail="result=accepted", ts="t",
        actor_kind=AuditActorKind.USER,
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_REVIEW)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER


def test_record_knowledge_conflict_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_conflict_action(
        record_id="conflict-cf1", actor_id="ai-1",
        action="discover_knowledge_conflict", target="cf1",
        detail="knowledge_a=k1;knowledge_b=k2", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_CONFLICT)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_require_human_actor_rejects_non_user() -> None:
    # 红线⑥：actor_kind 非 USER 一律拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor(AuditActorKind.AI)
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor(None)
    with pytest.raises(EnterpriseRedLineViolationError):
        require_human_actor("system")


def test_require_human_actor_accepts_user() -> None:
    # USER（枚举或字符串 "user"）通过
    require_human_actor(AuditActorKind.USER)
    require_human_actor("user")


def test_no_record_human_approval_method() -> None:
    # 红线⑥：审计服务不提供「代记人工批准」可用入口。AuditService 通过 _RedLineForbiddenMixin
    # 将 record_human_approval 列为 forbidden：访问即抛 EnterpriseRedLineViolationError，
    # 即不存在可被调用的 record_human_approval 方法。
    audit = AuditService(org_id="org-1")
    assert "record_human_approval" not in AuditService.__dict__
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(audit, "record_human_approval")


# ---- Phase 3.8.10：企业知识智能体编排层审计（任务7）----

def test_record_knowledge_agent_query_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_agent_query_action(
        record_id="agent-query-q1", actor_id="ai-1",
        action="understand_user_query", target="q1",
        detail="intent=ask_regulation;filters=1", ts="2026-08-05T00:00:00Z",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_QUERY)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_AGENT_QUERY
    assert recs[0].actor_kind == AuditActorKind.AI


def test_record_knowledge_agent_retrieve_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_agent_retrieve_action(
        record_id="agent-retrieve-q1", actor_id="ai-1",
        action="agent_retrieve_knowledge", target="q1",
        detail="matched=3;context_items=3;source_gaps=False", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_RETRIEVE)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_record_knowledge_agent_validate_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_agent_validate_action(
        record_id="agent-validate-v1", actor_id="ai-1",
        action="agent_validate_knowledge", target="v1",
        detail="query_id=q1;passed=True;issues=0;requires_human_review=true", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_VALIDATE)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


def test_record_knowledge_agent_draft_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_agent_draft_action(
        record_id="agent-draft-a1", actor_id="ai-1",
        action="agent_draft_answer", target="a1",
        detail="query_id=q1;references=3;confidence=0.6;requires_human_review=true", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_DRAFT)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


# ---- Phase 3.8.11：企业知识对话上下文与记忆层审计（任务5）----

def test_record_knowledge_conversation_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_conversation_action(
        record_id="conv-c1", actor_id="user-1",
        action="create_knowledge_conversation", target="c1",
        detail="title=风压规范咨询;user_id=u1", ts="2026-08-05T00:00:00Z",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_CONVERSATION)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_CONVERSATION
    # 会话由用户发起，默认 actor_kind → USER
    assert recs[0].actor_kind == AuditActorKind.USER


def test_record_knowledge_message_action_user_and_ai() -> None:
    audit = AuditService(org_id="org-1")
    # 用户提问：USER
    audit.record_knowledge_message_action(
        record_id="msg-m1", actor_id="user-1",
        action="append_knowledge_message", target="m1",
        detail="role=user;conversation_id=c1", ts="t",
        actor_kind=AuditActorKind.USER,
    )
    # AI 回答草稿：AI（必须带引用来源）
    audit.record_knowledge_message_action(
        record_id="msg-m2", actor_id="ai-1",
        action="append_knowledge_message", target="m2",
        detail="role=ai;references=2;requires_human_review=true", ts="t",
        actor_kind=AuditActorKind.AI,
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_MESSAGE)
    assert len(recs) == 2
    assert recs[0].actor_kind == AuditActorKind.USER
    assert recs[1].actor_kind == AuditActorKind.AI


def test_record_knowledge_memory_action_ai_propose() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_memory_action(
        record_id="mem-m1", actor_id="ai-1",
        action="propose_long_term_memory", target="m1",
        detail="source_conversation=c1;requires_human_review=true", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_MEMORY)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.AI


# ---- Phase 3.8.12：企业知识任务规划与多智能体工作流层审计（任务6）----

def test_record_knowledge_task_action_user_actor() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_task_action(
        record_id="task-t1", actor_id="user-1",
        action="create_knowledge_task", target="t1",
        detail="goal=风压规范咨询拆解;steps=3", ts="2026-08-06T00:00:00Z",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_TASK)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_TASK
    # 任务由用户发起，默认 actor_kind → USER
    assert recs[0].actor_kind == AuditActorKind.USER


def test_record_knowledge_subtask_action_ai_actor() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_subtask_action(
        record_id="sub-s1", actor_id="ai-1",
        action="create_knowledge_subtask", target="s1",
        detail="task_id=t1;agent_type=retrieval;requires_human_review=true", ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_SUBTASK)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_SUBTASK
    assert recs[0].actor_kind == AuditActorKind.AI


def test_record_knowledge_agent_workflow_action() -> None:
    audit = AuditService(org_id="org-1")
    audit.record_knowledge_agent_workflow_action(
        record_id="wf-w1", actor_id="ai-1",
        action="run_knowledge_agent_workflow", target="w1",
        detail="task_id=t1;agents=query,retrieve,validate,draft;requires_human_review=true",
        ts="t",
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_WORKFLOW)
    assert len(recs) == 1
    assert recs[0].category is AuditActionCategory.KNOWLEDGE_AGENT_WORKFLOW
    assert recs[0].actor_kind == AuditActorKind.AI
