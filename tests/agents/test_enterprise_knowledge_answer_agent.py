"""Phase 3.8.10 —— 测试4：回答起草智能体（KnowledgeAnswerAgent）。

覆盖：
- draft 产出 KnowledgeAnswerDraft，references = 上下文来源（非空），requires_human_review 强制 True。
- 审计落地 KNOWLEDGE_AGENT_DRAFT（AI）。
- 红线③/④/⑤：绝不自动应用知识 / 生成工程结论（forbidden 方法拦截）。
- 上下文无来源时，底层 KnowledgeAnswerDraft 强制拒绝无来源回答（ValueError）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.knowledge_validation_agent import (
    KnowledgeAgentValidationResult,
    KnowledgeValidationAgent,
)
from agents.enterprise.knowledge_answer_agent import KnowledgeAnswerAgent


def _ctx_with_sources() -> KnowledgeContext:
    items = [
        KnowledgeItem(
            knowledge_id="k1", title="规范", content="...", knowledge_type="regulation",
            source="import-reg", org_id="org-1", version="v2",
        )
    ]
    return KnowledgeContext(context_id="ctx-1", knowledge_items=items, org_id="org-1")


def _query() -> object:
    return KnowledgeQueryAgent(org_id="org-1").parse_query(
        query_id="q1", raw_query="查询规范"
    )


def _validation() -> KnowledgeAgentValidationResult:
    agent = KnowledgeValidationAgent(org_id="org-1")
    return agent.validate(
        validation_id="v1", query=_query(), context=_ctx_with_sources(),
        role=RoleKind.ENGINEER,
    )


def test_draft_has_references_and_requires_review() -> None:
    audit = AuditService(org_id="org-1")
    agent = KnowledgeAnswerAgent(org_id="org-1", audit=audit)
    draft = agent.draft(
        answer_id="a1", query=_query(), context=_ctx_with_sources(),
        validation=_validation(), content="请参考铝合金门窗设计规范。",
    )
    assert draft.references == ["import-reg"]
    assert draft.requires_human_review is True


def test_draft_records_audit() -> None:
    audit = AuditService(org_id="org-1")
    agent = KnowledgeAnswerAgent(org_id="org-1", audit=audit)
    agent.draft(
        answer_id="a2", query=_query(), context=_ctx_with_sources(),
        validation=_validation(),
    )
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_DRAFT)
    assert len(recs) == 1
    assert recs[0].actor_kind.value == "ai"


def test_draft_rejects_no_source_context() -> None:
    audit = AuditService(org_id="org-1")
    agent = KnowledgeAnswerAgent(org_id="org-1", audit=audit)
    items = [
        KnowledgeItem(
            knowledge_id="k2", title="无来源", content="...", knowledge_type="regulation",
            source="", org_id="org-1", version="v1",
        )
    ]
    ctx = KnowledgeContext(context_id="ctx-2", knowledge_items=items, org_id="org-1")
    with pytest.raises(ValueError):
        agent.draft(
            answer_id="a3", query=_query(), context=ctx, validation=_validation(),
        )


def test_answer_agent_forbids_apply_and_conclusion() -> None:
    from agents.enterprise.red_line import EnterpriseRedLineViolationError

    agent = KnowledgeAnswerAgent(org_id="org-1")
    for name in ("auto_apply_knowledge", "generate_engineering_conclusion", "approve"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(agent, name)
