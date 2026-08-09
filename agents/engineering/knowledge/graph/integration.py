"""Knowledge Repository → Knowledge Graph 单向同步（Phase 3.7.1 Task 4）。

流程（单向，不可回写）：
    KnowledgeItem（connector） → KnowledgeRepository（既有落库） → KnowledgeGraph（本层）

``KnowledgeRepositoryToGraphSync`` 从既有 ``KnowledgeRepository`` 读取当前版本
``KnowledgeItem``，将其落为 KnowledgeGraph 的 ``KnowledgeItem`` 节点，并依据其字段
派生关系边（authored_by / sourced_from / parent_child / basis）。

- 单向：图谱不回写 Repository；Repository 仍是唯一事实源（与 3.3.8 一致）。
- 不编造：仅在目标标识符非 pending 时创建**存根节点**（仅承载标识符，value 恒 pending），
  不填任何真实参数；pending 标识符直接跳过对应边，避免伪造。
- 红线：不写 verified.json、不开启 engineering_enabled、不输出 engineering_approved、
  不代签（signs 边由真实专家经正式流程驱动，本同步仅建 authored_by/witnessed_by 之类观察边）。

依赖方向：本模块 import 既有 ``repository.KnowledgeRepository`` 与 graph 包；
graph 包不反向 import repository，保持无循环依赖。
"""

from __future__ import annotations

from typing import Any

from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.graph.entities import (
    ExpertEntity,
    KnowledgeGraphEntityType,
    KnowledgeItemEntity,
    SourceRefEntity,
    ThresholdEntity,
    entity_to_node,
)
from agents.engineering.knowledge.graph.relationships import (
    GraphEdge,
    KnowledgeGraphRelationType,
)
from agents.engineering.knowledge.repository import KnowledgeRepository

# 同步产生的派生边类型（观察/关联类，非签署类）。
_SYNC_OBSERVATION_EDGE_TYPES = {
    KnowledgeGraphRelationType.AUTHORED_BY.value,
    KnowledgeGraphRelationType.WITNESSED_BY.value,
    KnowledgeGraphRelationType.SOURCED_FROM.value,
    KnowledgeGraphRelationType.CITES.value,
    KnowledgeGraphRelationType.PARENT_CHILD.value,
    KnowledgeGraphRelationType.BASIS.value,
    KnowledgeGraphRelationType.USED_BY.value,
}


def _edge_id(source_id: str, relation_type: str, target_id: str) -> str:
    return f"E-{relation_type}-{source_id}__{target_id}"


class KnowledgeRepositoryToGraphSync:
    """单向同步器：Repository → Graph。"""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def _ensure_stub(
        self, *, node_id: str, entity_type: str, attrs: dict[str, Any], actor: str
    ) -> None:
        """仅当目标节点不存在时，建立**存根**节点（不覆盖既有）。"""
        if self._graph.exists(node_id):
            return
        from agents.engineering.knowledge.graph.entities import GraphNode

        stub = GraphNode(
            node_id=node_id,
            entity_type=entity_type,
            label=attrs.get("label", node_id),
            attributes=attrs,
            actor=actor,
            pending_build=(entity_type in (
                KnowledgeGraphEntityType.CASE.value,
                KnowledgeGraphEntityType.RULE.value,
            )),
        )
        # 计算哈希（避免 import 循环，直接复用 entity 工具）。
        from agents.engineering.knowledge.graph.entities import compute_node_hash

        stub.content_hash = compute_node_hash(stub)
        self._graph.add_node(stub, actor=actor)

    def _add_edge(self, edge: GraphEdge, *, actor: str) -> None:
        try:
            self._graph.add_edge(edge, actor=actor)
        except ValueError:
            # fail-closed 校验未过（如目标节点缺失/类型约束不符）→ 跳过该边，不静默改写。
            # 真实数据（pending 标识符）下多数派生边本就会被跳过。
            return

    def sync_item(
        self, repo: KnowledgeRepository, knowledge_id: str, *, actor: str = "repository_sync"
    ) -> list[str]:
        """同步单条 KnowledgeItem 及其派生关联边。

        返回本次新增/更新的图谱对象 id 列表（节点 + 边）。
        """
        item: KnowledgeItem | None = repo.get(knowledge_id)
        if item is None:
            raise KeyError(f"knowledge_id={knowledge_id!r} 不在 Repository 中")

        touched: list[str] = []
        # 1) KnowledgeItem 节点
        node = KnowledgeItemEntity(item).to_node(actor=actor)
        self._graph.add_node(node, actor=actor)
        touched.append(item.knowledge_id)

        # 2) authored_by：author 非 pending 时建专家存根 + 边
        if item.author and item.author != PENDING_PLACEHOLDER:
            self._ensure_stub(
                node_id=item.author,
                entity_type=KnowledgeGraphEntityType.EXPERT.value,
                attrs=ExpertEntity(expert_id=item.author).to_node(actor=actor).attributes,
                actor=actor,
            )
            self._add_edge(
                GraphEdge(
                    edge_id=_edge_id(item.knowledge_id, "authored_by", item.author),
                    relation_type=KnowledgeGraphRelationType.AUTHORED_BY.value,
                    source_id=item.knowledge_id,
                    target_id=item.author,
                    attributes={},
                ),
                actor=actor,
            )
            touched.append(_edge_id(item.knowledge_id, "authored_by", item.author))

        # 3) sourced_from / cites：source 非 pending 时建 SourceRef 存根 + 边
        if item.source and item.source != PENDING_PLACEHOLDER:
            sr = SourceRefEntity(source_ref_id=item.source)
            self._ensure_stub(
                node_id=item.source,
                entity_type=KnowledgeGraphEntityType.SOURCE_REF.value,
                attrs=sr.to_node(actor=actor).attributes,
                actor=actor,
            )
            for rel in (
                KnowledgeGraphRelationType.SOURCED_FROM.value,
                KnowledgeGraphRelationType.CITES.value,
            ):
                self._add_edge(
                    GraphEdge(
                        edge_id=_edge_id(item.knowledge_id, rel, item.source),
                        relation_type=rel,
                        source_id=item.knowledge_id,
                        target_id=item.source,
                        attributes={"standard": "", "clause": ""},
                    ),
                    actor=actor,
                )
                touched.append(_edge_id(item.knowledge_id, rel, item.source))

        # 4) parent_child：parent 已入图时建边
        if (
            item.parent_knowledge_id
            and item.parent_knowledge_id != PENDING_PLACEHOLDER
            and self._graph.exists(item.parent_knowledge_id)
        ):
            self._add_edge(
                GraphEdge(
                    edge_id=_edge_id(item.knowledge_id, "parent_child", item.parent_knowledge_id),
                    relation_type=KnowledgeGraphRelationType.PARENT_CHILD.value,
                    source_id=item.knowledge_id,
                    target_id=item.parent_knowledge_id,
                    attributes={"no_cycle": True},
                ),
                actor=actor,
            )
            touched.append(_edge_id(item.knowledge_id, "parent_child", item.parent_knowledge_id))

        # 5) basis / used_by：linked_entities（阈值 id）非 pending 时建 Threshold 存根 + 边
        for ent in item.linked_entities or []:
            if not ent or ent == PENDING_PLACEHOLDER:
                continue
            thr = ThresholdEntity(threshold_id=ent, domain=item.domain)
            self._ensure_stub(
                node_id=ent,
                entity_type=KnowledgeGraphEntityType.THRESHOLD.value,
                attrs=thr.to_node(actor=actor).attributes,
                actor=actor,
            )
            self._add_edge(
                GraphEdge(
                    edge_id=_edge_id(item.knowledge_id, "basis", ent),
                    relation_type=KnowledgeGraphRelationType.BASIS.value,
                    source_id=item.knowledge_id,
                    target_id=ent,
                    attributes={},
                ),
                actor=actor,
            )
            touched.append(_edge_id(item.knowledge_id, "basis", ent))

        return touched

    def sync_all(self, repo: KnowledgeRepository, *, actor: str = "repository_sync") -> list[str]:
        """同步 Repository 内全部当前版本 KnowledgeItem。"""
        touched: list[str] = []
        for item in repo.query():
            touched.extend(self.sync_item(repo, item.knowledge_id, actor=actor))
        return touched


__all__ = [
    "KnowledgeRepositoryToGraphSync",
    "SYNC_OBSERVATION_EDGE_TYPES",
]
