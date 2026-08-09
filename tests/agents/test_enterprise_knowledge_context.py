"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 测试4：知识上下文可追溯（任务3，Phase 3.8.9）。

覆盖（KnowledgeContext / KnowledgeTrace）：
- __post_init__ 自动派生 sources / versions / trace（所有知识须可追溯）。
- trace 逐条绑定知识项（knowledge_id / source / version / org_id）。
- has_source_gaps 识别缺来源项。
- item_ids 返回上下文内全部知识项 id。
- 上下文须携带知识项（空项集合仍构造成功但 trace 为空）。
"""

from __future__ import annotations

from agents.enterprise.knowledge_context import KnowledgeContext, KnowledgeTrace
from agents.enterprise.knowledge_retrieval import KnowledgeItem


def _item(kid: str, source: str, version: str = "") -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=kid, title=kid, content="x", knowledge_type="manual",
        source=source, org_id="org-1", version=version,
    )


def test_context_derives_sources_versions_trace() -> None:
    items = [
        _item("k1", "manual", "v2"),
        _item("k2", "candidate-x", "v1"),
    ]
    ctx = KnowledgeContext(context_id="c1", knowledge_items=items, org_id="org-1")
    assert sorted(ctx.sources) == ["candidate-x", "manual"]
    assert sorted(ctx.versions) == ["v1", "v2"]
    assert len(ctx.trace) == 2


def test_context_trace_per_item() -> None:
    items = [_item("k1", "manual", "v2")]
    ctx = KnowledgeContext(context_id="c1", knowledge_items=items, org_id="org-1")
    t = ctx.trace[0]
    assert isinstance(t, KnowledgeTrace)
    assert t.knowledge_id == "k1"
    assert t.source == "manual"
    assert t.version == "v2"
    assert t.org_id == "org-1"


def test_context_has_source_gaps_true() -> None:
    items = [_item("k1", ""), _item("k2", "manual")]
    ctx = KnowledgeContext(context_id="c1", knowledge_items=items, org_id="org-1")
    assert ctx.has_source_gaps() is True


def test_context_has_source_gaps_false() -> None:
    items = [_item("k1", "manual"), _item("k2", "candidate-x")]
    ctx = KnowledgeContext(context_id="c1", knowledge_items=items, org_id="org-1")
    assert ctx.has_source_gaps() is False


def test_context_item_ids() -> None:
    items = [_item("k1", "manual"), _item("k2", "candidate-x")]
    ctx = KnowledgeContext(context_id="c1", knowledge_items=items, org_id="org-1")
    assert ctx.item_ids() == ["k1", "k2"]


def test_context_empty_items_ok() -> None:
    ctx = KnowledgeContext(context_id="c1", knowledge_items=[], org_id="org-1")
    assert ctx.sources == []
    assert ctx.versions == []
    assert ctx.trace == []
