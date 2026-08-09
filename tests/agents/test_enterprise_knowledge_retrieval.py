"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试2：检索引擎（任务2，Phase 3.8.9）。

覆盖（KnowledgeItem / KnowledgeRetrievalEngine）：
- index 注册已存在知识项（仅元数据目录化，绝不写知识资产，red line ③）。
- search 按相关度降序返回候选知识；empty query 返回空。
- semantic_match 词元重叠度打分（启发式，确定性）。
- filter_by_permission 按角色可见性过滤（默认拒绝）。
- retrieve_context 拼装可追溯 KnowledgeContext（sources / versions / trace）。
- 红线④/⑤：引擎不存在生成工程结论的入口（generate_engineering_conclusion 被拦截）。
- 检索如实记录 KNOWLEDGE_RETRIEVAL 审计。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import RoleKind
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_retrieval import (
    KnowledgeItem,
    KnowledgeRetrievalEngine,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _engine(org_id: str = "org-1") -> KnowledgeRetrievalEngine:
    return KnowledgeRetrievalEngine(org_id=org_id, audit=AuditService(org_id=org_id))


def _item(kid: str, content: str, ktype: str, source: str = "manual", version: str = "") -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=kid, title=kid, content=content,
        knowledge_type=ktype, source=source, org_id="org-1", version=version,
    )


def test_index_registers_item() -> None:
    eng = _engine()
    it = eng.index(item=_item("k1", "幕墙 设计", "design_spec"))
    assert eng.list_items()[0].knowledge_id == "k1"
    assert it.org_id == "org-1"


def test_search_ranks_by_relevance() -> None:
    eng = _engine()
    eng.index(item=_item("k1", "建筑外窗 开窗面积 通风 计算 规范", "regulation"))
    eng.index(item=_item("k2", "玻璃幕墙 立面 设计", "design_spec"))
    results = eng.search(query_text="开窗面积 通风 计算", role=RoleKind.ENGINEER)
    assert results[0].knowledge_id == "k1"


def test_search_empty_query_returns_nothing() -> None:
    eng = _engine()
    eng.index(item=_item("k1", "幕墙 设计", "design_spec"))
    assert eng.search(query_text="   ", role=RoleKind.ENGINEER) == []


def test_semantic_match_scores_descending() -> None:
    eng = _engine()
    eng.index(item=_item("k1", "开窗面积 通风 计算", "regulation"))
    eng.index(item=_item("k2", "幕墙 立面", "design_spec"))
    scored = eng.semantic_match(query_text="开窗面积 通风 计算")
    assert scored[0][0].knowledge_id == "k1"
    assert scored[0][1] >= scored[1][1] > 0.0


def test_filter_by_permission_default_deny() -> None:
    eng = _engine()
    # feedback 类型对 ENGINEER 不可见（角色策略默认拒绝）
    eng.index(item=_item("k1", "用户反馈 内容", "feedback"))
    eng.index(item=_item("k2", "开窗面积 规范", "regulation"))
    out = eng.filter_by_permission(role=RoleKind.ENGINEER, items=eng.list_items())
    assert [it.knowledge_id for it in out] == ["k2"]


def test_retrieve_context_builds_traceable() -> None:
    eng = _engine()
    eng.index(item=_item("k1", "开窗面积 规范", "regulation", source="manual", version="v2"))
    results = eng.search(query_text="开窗面积", role=RoleKind.ENGINEER)
    ctx = eng.retrieve_context(query_id="q1", items=results)
    assert isinstance(ctx, KnowledgeContext)
    assert ctx.sources == ["manual"]
    assert ctx.versions == ["v2"]
    assert ctx.trace[0].knowledge_id == "k1"
    assert ctx.trace[0].source == "manual"
    assert ctx.trace[0].version == "v2"


def test_engine_no_generate_engineering_conclusion() -> None:
    eng = _engine()
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = eng.generate_engineering_conclusion  # type: ignore[attr-defined]


def test_search_records_retrieval_audit() -> None:
    eng = _engine()
    eng.index(item=_item("k1", "开窗面积 规范", "regulation"))
    eng.search(query_text="开窗面积", role=RoleKind.ENGINEER)
    recs = eng._audit.query(category=AuditActionCategory.KNOWLEDGE_RETRIEVAL)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER
