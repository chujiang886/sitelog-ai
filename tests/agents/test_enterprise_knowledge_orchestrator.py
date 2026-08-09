"""Phase 3.8.10 —— 测试5：智能体编排器（KnowledgeAgentOrchestrator）。

覆盖：
- run() 串起 query→retrieve→validate→draft，返回待人工复核草稿。
- agent_event_log 含 4 个步骤事件（query/retrieve/validate/draft）。
- 四个子智能体共享同一 audit：编排后应有 4 条 KNOWLEDGE_AGENT_* 审计记录。
- 返回草稿 requires_human_review 强制 True。
- 红线①/⑤：safety_invariants_ok 失败时构造即抛（fail-closed）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_agent_orchestrator import KnowledgeAgentOrchestrator
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    load_engineering_enabled,
)


@pytest.fixture
def seeded_org() -> KnowledgeAgentOrchestrator:
    audit = AuditService(org_id="org-1")
    org = KnowledgeAgentOrchestrator(org_id="org-1", audit=audit)
    org._retrieval_agent._engine.index(
        item=KnowledgeItem(
            knowledge_id="k1", title="铝合金门窗设计规范", content="规范正文",
            knowledge_type="regulation", source="import-reg", org_id="org-1",
            version="v2", tags=["window"],
        )
    )
    return org


def test_run_produces_draft_and_event_log(seeded_org: KnowledgeAgentOrchestrator) -> None:
    draft = seeded_org.run(
        query_id="q1", raw_query="查询铝合金门窗设计规范", answer_id="a1",
        role=RoleKind.ENGINEER,
    )
    assert draft.requires_human_review is True
    log = seeded_org.agent_event_log()
    steps = [e.step for e in log]
    assert steps == ["query", "retrieve", "validate", "draft"]
    assert all(e.status == "ok" for e in log)


def test_run_records_four_agent_audits(seeded_org: KnowledgeAgentOrchestrator) -> None:
    seeded_org.run(
        query_id="q2", raw_query="查询规范", answer_id="a2", role=RoleKind.ENGINEER,
    )
    audit: AuditService = seeded_org._audit
    cats = {AuditActionCategory.KNOWLEDGE_AGENT_QUERY,
            AuditActionCategory.KNOWLEDGE_AGENT_RETRIEVE,
            AuditActionCategory.KNOWLEDGE_AGENT_VALIDATE,
            AuditActionCategory.KNOWLEDGE_AGENT_DRAFT}
    for cat in cats:
        recs = audit.query(category=cat)
        assert len(recs) == 1, f"缺少审计类别 {cat}"
        assert recs[0].actor_kind == AuditActorKind.AI


def test_orchestrator_fail_closed_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        KnowledgeAgentOrchestrator(org_id="org-1")
