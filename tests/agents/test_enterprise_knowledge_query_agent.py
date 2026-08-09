"""Phase 3.8.10 —— 测试1：查询理解智能体（KnowledgeQueryAgent）。

覆盖：
- parse_query 产出 KnowledgeQuery（intent + filters + org_id）。
- identify_intent 关键词确定性识别（规范/设计/案例/手册/治理/反馈/unknown）。
- extract_filters 抽取 knowledge_type 提示 + 拉丁标签。
- 审计落地 KNOWLEDGE_AGENT_QUERY（AI）。
- 红线④/⑤：本智能体不持有 generate_engineering_conclusion（访问即抛红线违例）。
"""

from __future__ import annotations

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.knowledge_query_agent import (
    KnowledgeQuery,
    KnowledgeQueryAgent,
)


def _agent(org_id: str = "org-1") -> KnowledgeQueryAgent:
    audit = AuditService(org_id=org_id)
    return KnowledgeQueryAgent(org_id=org_id, audit=audit)


def test_parse_query_basic() -> None:
    agent = _agent()
    q = agent.parse_query(query_id="q1", raw_query="请查询铝合金门窗设计规范")
    assert isinstance(q, KnowledgeQuery)
    assert q.query_id == "q1"
    assert q.intent == "ask_regulation"
    assert q.filters.get("knowledge_type") == "regulation"
    assert q.org_id == "org-1"


def test_identify_intent_variants() -> None:
    agent = _agent()
    assert agent.identify_intent(raw_query="设计图纸与型材怎么选") == "ask_design_spec"
    assert agent.identify_intent(raw_query="有没有相似的工程案例") == "ask_case"
    assert agent.identify_intent(raw_query="操作手册在哪里") == "ask_manual"
    assert agent.identify_intent(raw_query="治理流程制度") == "ask_governance"
    assert agent.identify_intent(raw_query="用户反馈复盘") == "ask_feedback"
    assert agent.identify_intent(raw_query="随便聊聊天气") == "unknown"


def test_extract_filters_latin_tags() -> None:
    agent = _agent()
    f = agent.extract_filters(raw_query="铝合金 window thermal", intent="ask_design_spec")
    assert f.get("knowledge_type") == "design_spec"
    assert "window" in f.get("tags", [])
    assert "thermal" in f.get("tags", [])


def test_parse_query_records_audit() -> None:
    audit = AuditService(org_id="org-1")
    agent = KnowledgeQueryAgent(org_id="org-1", audit=audit)
    agent.parse_query(query_id="q2", raw_query="查询规范")
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_QUERY)
    assert len(recs) == 1
    assert recs[0].action == "understand_user_query"


def test_query_agent_forbids_engineering_conclusion() -> None:
    from agents.enterprise.red_line import EnterpriseRedLineViolationError

    agent = _agent()
    for name in ("generate_engineering_conclusion", "engineering_approved", "auto_apply_knowledge"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(agent, name)


import pytest  # noqa: E402
