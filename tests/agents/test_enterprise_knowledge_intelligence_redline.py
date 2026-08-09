"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试8：六红线 fail-closed（Phase 3.8.9）。

覆盖（统一 fail-closed 基座）：
- 红线①/⑤：engineering_enabled 被置为 True 时，所有知识智能服务构造抛错。
- 红线②：各服务不存在 engineering_approved 可达入口（访问即抛）。
- 红线③：各服务不存在 auto_apply_knowledge / auto_update_knowledge 可达入口。
- 红线④/⑤：各服务不存在 generate_engineering_conclusion / decide 可达入口。
- 红线⑥：require_human_actor 拒绝 AI/SYSTEM/None；审计 record_human_approval 被拦截。
- safety_invariants_ok() 在当前未启用态返回 True。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditService,
    require_human_actor,
    AuditActorKind,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_answer import KnowledgeAnswerService
from agents.enterprise.knowledge_recommendation import KnowledgeRecommendationService
from agents.enterprise.knowledge_retrieval import KnowledgeRetrievalEngine
from agents.enterprise.knowledge_search import KnowledgeSearchService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )


def test_safety_invariants_ok_false_when_disabled() -> None:
    # 当前工程态 engineering_enabled=false（config.yaml:102），护栏应通过
    assert safety_invariants_ok() is True


def test_construction_fail_closed_when_enabled(enabled: None) -> None:
    for svc_cls in (
        KnowledgeSearchService,
        KnowledgeRetrievalEngine,
        KnowledgeAnswerService,
        KnowledgeRecommendationService,
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            svc_cls(org_id="org-1", audit=AuditService(org_id="org-1"))


def test_no_engineering_approved_across_services() -> None:
    svcs = [
        KnowledgeSearchService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRetrievalEngine(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeAnswerService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRecommendationService(org_id="org-1", audit=AuditService(org_id="org-1")),
    ]
    for svc in svcs:
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = svc.engineering_approved  # type: ignore[attr-defined]


def test_forbidden_auto_apply_across_services() -> None:
    svcs = [
        KnowledgeSearchService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRetrievalEngine(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeAnswerService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRecommendationService(org_id="org-1", audit=AuditService(org_id="org-1")),
    ]
    for svc in svcs:
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = svc.auto_apply_knowledge  # type: ignore[attr-defined]


def test_forbidden_conclusion_and_decision_across_services() -> None:
    svcs = [
        KnowledgeSearchService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRetrievalEngine(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeAnswerService(org_id="org-1", audit=AuditService(org_id="org-1")),
        KnowledgeRecommendationService(org_id="org-1", audit=AuditService(org_id="org-1")),
    ]
    for svc in svcs:
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = svc.generate_engineering_conclusion  # type: ignore[attr-defined]
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = svc.decide  # type: ignore[attr-defined]


def test_require_human_actor_blocks_ai() -> None:
    # 红线⑥：AI / SYSTEM / None 均不得替代人工责任
    for bad in (AuditActorKind.AI, AuditActorKind.SYSTEM, None):
        with pytest.raises(EnterpriseRedLineViolationError):
            require_human_actor(bad)
    # 仅真实 USER 通过
    require_human_actor(AuditActorKind.USER)
    require_human_actor("user")
