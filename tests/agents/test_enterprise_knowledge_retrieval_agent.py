"""Phase 3.8.10 —— 测试2：检索智能体（KnowledgeRetrievalAgent）。

覆盖：
- retrieve 调用引擎召回候选，产出 KnowledgeContext（sources/versions/trace 自动派生）。
- 上下文溯源非空、来源可追溯（任务2 核心要求）。
- 审计落地 KNOWLEDGE_AGENT_RETRIEVE（AI）。
- 红线③/⑤：本智能体不持有 auto_apply_knowledge / generate_engineering_conclusion。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_query_agent import KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.knowledge_retrieval_agent import KnowledgeRetrievalAgent


def _seed(engine) -> None:
    engine.index(
        item=KnowledgeItem(
            knowledge_id="k1", title="铝合金门窗设计规范", content="铝合金型材选用规范正文",
            knowledge_type="regulation", source="import-reg", org_id="org-1",
            version="v2", tags=["window"],
        )
    )
    engine.index(
        item=KnowledgeItem(
            knowledge_id="k2", title="某工程案例", content="工程实例描述",
            knowledge_type="case", source="case-lib", org_id="org-1",
            version="v1", tags=["case"],
        )
    )


def _retrieval_agent(org_id: str = "org-1"):
    audit = AuditService(org_id=org_id)
    agent = KnowledgeRetrievalAgent(org_id=org_id, audit=audit)
    _seed(agent._engine)
    return agent, audit


def test_retrieve_returns_traceable_context() -> None:
    agent, _ = _retrieval_agent()
    q = KnowledgeQueryAgent(org_id="org-1").parse_query(
        query_id="q1", raw_query="查询铝合金门窗设计规范"
    )
    ctx = agent.retrieve(query=q, role=RoleKind.ENGINEER, top_k=5)
    assert ctx.knowledge_items
    assert ctx.trace  # 溯源非空
    assert ctx.sources  # 来源可追溯
    assert "import-reg" in ctx.sources
    assert not ctx.has_source_gaps()


def test_retrieve_records_audit() -> None:
    agent, audit = _retrieval_agent()
    q = KnowledgeQueryAgent(org_id="org-1").parse_query(
        query_id="q2", raw_query="查询规范"
    )
    agent.retrieve(query=q, role=RoleKind.ENGINEER)
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_RETRIEVE)
    assert len(recs) == 1
    assert recs[0].actor_kind.value == "ai"


def test_retrieval_agent_forbids_apply_and_conclusion() -> None:
    from agents.enterprise.red_line import EnterpriseRedLineViolationError

    agent, _ = _retrieval_agent()
    for name in ("auto_apply_knowledge", "generate_engineering_conclusion", "approve"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(agent, name)
