"""Phase 3.8.10 —— 测试3：校验智能体（KnowledgeValidationAgent）。

覆盖：
- 上下文来源完整 + 角色可见 → passed=True，requires_human_review 强制 True（红线⑥）。
- 上下文存在缺来源项 → 产出 source_gap issue，passed=False。
- 角色不可见类型 → permission_denied issue。
- 校验结果**绝不**自动批准回答（无 approve，且 requires_human_review 恒 True）。
- 审计落地 KNOWLEDGE_AGENT_VALIDATE（AI）。
- 红线②/④/⑥：本智能体不持有 approve / auto_approve / engineering_approved。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_context import KnowledgeContext, KnowledgeTrace
from agents.enterprise.knowledge_query_agent import KnowledgeQueryAgent
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.knowledge_validation_agent import KnowledgeValidationAgent


def _ctx(items: list[KnowledgeItem]) -> KnowledgeContext:
    return KnowledgeContext(
        context_id="ctx-1",
        knowledge_items=items,
        org_id="org-1",
    )


def _agent():
    audit = AuditService(org_id="org-1")
    return KnowledgeValidationAgent(org_id="org-1", audit=audit), audit


def _query() -> object:
    return KnowledgeQueryAgent(org_id="org-1").parse_query(
        query_id="q1", raw_query="查询规范"
    )


def test_validate_pass() -> None:
    agent, _ = _agent()
    items = [
        KnowledgeItem(
            knowledge_id="k1", title="规范", content="...", knowledge_type="regulation",
            source="import-reg", org_id="org-1", version="v2",
        )
    ]
    ctx = _ctx(items)
    res = agent.validate(
        validation_id="v1", query=_query(), context=ctx, role=RoleKind.ENGINEER
    )
    assert res.passed is True
    assert res.requires_human_review is True
    assert res.issues == []


def test_validate_source_gap_blocks() -> None:
    agent, _ = _agent()
    items = [
        KnowledgeItem(
            knowledge_id="k2", title="无来源", content="...", knowledge_type="regulation",
            source="", org_id="org-1", version="v1",
        )
    ]
    ctx = _ctx(items)
    res = agent.validate(validation_id="v2", query=_query(), context=ctx)
    assert res.passed is False
    assert any(i.startswith("source_gap") for i in res.issues)


def test_validate_permission_denied() -> None:
    agent, _ = _agent()
    items = [
        KnowledgeItem(
            knowledge_id="k3", title="设计", content="...", knowledge_type="design_spec",
            source="ds", org_id="org-1", version="v1",
        )
    ]
    ctx = _ctx(items)
    # REVIEWER 不可见 design_spec（其可见集为 governance/feedback/regulation）
    res = agent.validate(
        validation_id="v3", query=_query(), context=ctx, role=RoleKind.REVIEWER
    )
    assert any(i.startswith("permission_denied") for i in res.issues)


def test_validate_records_audit() -> None:
    agent, audit = _agent()
    items = [
        KnowledgeItem(
            knowledge_id="k1", title="规范", content="...", knowledge_type="regulation",
            source="import-reg", org_id="org-1", version="v2",
        )
    ]
    agent.validate(validation_id="v4", query=_query(), context=_ctx(items))
    recs = audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_VALIDATE)
    assert len(recs) == 1
    assert recs[0].actor_kind.value == "ai"


def test_validation_agent_forbids_approve() -> None:
    from agents.enterprise.red_line import EnterpriseRedLineViolationError

    agent, _ = _agent()
    for name in ("approve", "auto_approve", "engineering_approved"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(agent, name)
