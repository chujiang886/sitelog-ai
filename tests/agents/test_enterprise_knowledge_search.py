"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试1：检索查询（任务1，Phase 3.8.9）。

覆盖（KnowledgeSearchQuery / KnowledgeSearchService）：
- KnowledgeSearchQuery 强制 org_id（任务1 权限隔离）。
- create_query 在组织作用域登记查询，并如实记录 KNOWLEDGE_SEARCH 审计。
- run / run_with_context 返回**候选知识**（只检索，绝不生成工程结论）。
- 跨组织隔离（_get_scoped）。
- forbidden 方法拦截（auto_apply_knowledge / generate_engineering_conclusion / decide 等）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.knowledge_search import (
    KnowledgeSearchQuery,
    KnowledgeSearchService,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> KnowledgeSearchService:
    return KnowledgeSearchService(org_id=org_id, audit=AuditService(org_id=org_id))


def _item(kid: str, content: str, ktype: str, source: str = "manual") -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=kid, title=kid, content=content,
        knowledge_type=ktype, source=source, org_id="org-1",
    )


def test_query_dataclass_requires_org_id() -> None:
    with pytest.raises(ValueError):
        KnowledgeSearchQuery(
            query_id="q1", org_id="", user_id="u1", query_text="开窗面积",
        )


def test_create_query_registers_with_org() -> None:
    svc = _svc()
    q = svc.create_query(
        query_id="q1", user_id="u1", query_text="开窗面积 计算",
    )
    assert q.org_id == "org-1"
    assert q.user_id == "u1"
    # 读取在组织作用域内
    assert svc.get_query(query_id="q1").query_id == "q1"


def test_create_query_records_search_audit() -> None:
    svc = _svc()
    svc.create_query(query_id="q1", user_id="u1", query_text="幕墙 设计")
    recs = svc._audit.query(category=AuditActionCategory.KNOWLEDGE_SEARCH)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER
    assert recs[0].target == "q1"


def test_run_returns_candidate_items() -> None:
    svc = _svc()
    svc._engine.index(item=_item("k1", "建筑外窗 开窗面积 通风 计算 规范", "regulation"))
    svc._engine.index(item=_item("k2", "钢结构 梁柱 节点 支座", "design_spec"))
    svc.create_query(query_id="q1", user_id="u1", query_text="开窗面积 通风 计算")
    results = svc.run(query_id="q1", role=RoleKind.ENGINEER, top_k=5)
    assert [it.knowledge_id for it in results] == ["k1"]


def test_run_with_context_builds_traceable() -> None:
    svc = _svc()
    svc._engine.index(item=_item("k1", "建筑外窗 开窗面积 通风", "regulation", source="manual"))
    svc.create_query(query_id="q1", user_id="u1", query_text="开窗面积 通风")
    ctx = svc.run_with_context(query_id="q1", role=RoleKind.ENGINEER)
    assert ctx.context_id == "ctx-q1"
    assert ctx.item_ids() == ["k1"]
    assert "manual" in ctx.sources
    assert len(ctx.trace) == 1


def test_run_only_returns_candidates_not_conclusions() -> None:
    svc = _svc()
    # 红线④/⑤：检索结果仅为候选，结构上不存在生成工程结论的入口
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.generate_engineering_conclusion  # type: ignore[attr-defined]


def test_cross_org_query_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.create_query(query_id="q1", user_id="u1", query_text="x")
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get_query(query_id="q1")


def test_forbidden_auto_knowledge_methods() -> None:
    svc = _svc()
    for name in (
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
        "publish",
        "merge",
        "apply",
        "write",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_forbidden_decision_methods() -> None:
    svc = _svc()
    for name in (
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "generate_engineering_conclusion",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)
