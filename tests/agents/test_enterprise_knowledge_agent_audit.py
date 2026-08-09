"""Phase 3.8.10 —— 测试7：智能体编排层审计（AuditService 4 个新增类别 + 全链路审计轨迹）。

覆盖：
- AuditActionCategory 含 4 个 KNOWLEDGE_AGENT_* 成员。
- 经由 EnterpriseOperationLayer 聚合门面跑通 orchestrator，验证审计轨迹：
  query/retrieve/validate/draft 四类 AI 动作齐全，且复核为 USER 动作。
- 无 record_human_approval（红线⑥：不提供「代记人工批准」入口）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.service import EnterpriseOperationLayer


def test_agent_categories_present() -> None:
    for name in (
        "KNOWLEDGE_AGENT_QUERY", "KNOWLEDGE_AGENT_RETRIEVE",
        "KNOWLEDGE_AGENT_VALIDATE", "KNOWLEDGE_AGENT_DRAFT",
    ):
        assert hasattr(AuditActionCategory, name)


def test_full_audit_trail_via_layer() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    layer.knowledge_agent_orchestrator._retrieval_agent._engine.index(
        item=__import__(
            "agents.enterprise.knowledge_retrieval", fromlist=["KnowledgeItem"]
        ).KnowledgeItem(
            knowledge_id="k1", title="规范", content="...", knowledge_type="regulation",
            source="import-reg", org_id="org-1", version="v2",
        )
    )
    layer.knowledge_agent_orchestrator.run(
        query_id="q1", raw_query="查询铝合金门窗设计规范", answer_id="a1",
        role=RoleKind.ENGINEER,
    )
    cats = (
        AuditActionCategory.KNOWLEDGE_AGENT_QUERY,
        AuditActionCategory.KNOWLEDGE_AGENT_RETRIEVE,
        AuditActionCategory.KNOWLEDGE_AGENT_VALIDATE,
        AuditActionCategory.KNOWLEDGE_AGENT_DRAFT,
    )
    for cat in cats:
        assert len(layer.audit.query(category=cat)) == 1

    # 真实人工复核 → USER 动作（复核动作如实标注为 USER，绝不伪造）
    layer.knowledge_answer_review.submit_review_by_user(
        review_id="r1", answer_id="a1", reviewer_user_id="user-expert-1",
        decision="accepted", comment="可参考",
    )
    user_recs = layer.audit.query(actor_kind=AuditActorKind.USER)
    review_recs = [r for r in user_recs if r.action.startswith("submit_knowledge_answer_review")]
    assert len(review_recs) == 1
    assert review_recs[0].actor_kind == AuditActorKind.USER


def test_no_record_human_approval_on_audit() -> None:
    audit = AuditService(org_id="org-1")
    assert "record_human_approval" not in AuditService.__dict__
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(audit, "record_human_approval")
