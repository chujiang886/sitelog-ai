"""Knowledge Graph Conflict Detector（Phase 3.7.1 Task 5）。

在既有 ``KnowledgeConflictDetector``（3.3.9，review_required 恒 True）之上，
扩展图谱级冲突检测：在 ``KnowledgeGraphRepository`` 的节点/边之上发现潜在冲突。

冲突类型：
- duplicate_node   ：同 entity_type + 同 label 但不同 node_id（疑似重复实体）；
- dangling_edge    ：边的起/止节点缺失（不应发生，因 add_edge 已校验，复核用）；
- pending_build_edge：pending_build（Case/Rule 待建）节点被生产类关系（basis/used_by/applies）引用；
- type_mismatch     ：边的实体类型约束与 RELATIONSHIP_SPECS 不符（复核用）。

红线约束（延续 3.3.9）：
- 所有冲突 ``review_required`` 恒定 ``True``，**绝不**自动解决；
- 本类**不提供** merge / delete / approve 任何方法（禁止自动 merge/delete/approve）；
- detect() 不写盘、不调 add_node/add_edge、不输出任何解决结论；
  冲突仅进入"待人工复核"队列（AI 不代专家审核）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agents.engineering.knowledge.graph.entities import (
    GraphNode,
    KnowledgeGraphEntityType,
)
from agents.engineering.knowledge.graph.relationships import (
    RELATIONSHIP_SPECS,
    GraphEdge,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository

CONFLICT_DUPLICATE_NODE: str = "duplicate_node"
CONFLICT_DANGLING_EDGE: str = "dangling_edge"
CONFLICT_PENDING_BUILD_EDGE: str = "pending_build_edge"
CONFLICT_TYPE_MISMATCH: str = "type_mismatch"

# 生产类关系：pending_build 节点不应被其引用（属待建骨架，禁止参与工程判定）。
_PRODUCTION_RELATIONS = {
    "basis",
    "used_by",
    "applies",
}


@dataclass
class GraphConflictReport:
    """一条图谱冲突报告；review_required 恒定 True（永不自动解决）。"""

    conflict_id: str
    scope: str
    conflict_type: str
    entity_a: str
    entity_b: str
    detail: str
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "scope": self.scope,
            "conflict_type": self.conflict_type,
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "detail": self.detail,
            "review_required": self.review_required,
        }


class KnowledgeGraphConflictDetector:
    """图谱冲突检测（只读，review_required 恒 True）。

    注意：本类**不提供**任何 merge / delete / approve 方法。冲突只能被标记，
    只能由人工在 ESW 窗口/正式审核流程中处置。
    """

    def detect(self, graph: KnowledgeGraphRepository) -> list[GraphConflictReport]:
        reports: list[GraphConflictReport] = []
        nodes: dict[str, GraphNode] = {
            nid: graph.get_node(nid) for nid in graph._nodes.keys()
        }
        # 1) duplicate_node：同 entity_type + 同 label 不同 node_id
        seen: dict[tuple[str, str], str] = {}
        for nid, node in nodes.items():
            if node is None:
                continue
            key = (node.entity_type, node.label)
            if key in seen and seen[key] != nid:
                reports.append(
                    self._make(
                        CONFLICT_DUPLICATE_NODE,
                        "node",
                        seen[key],
                        nid,
                        f"同 entity_type={node.entity_type!r} 同 label={node.label!r} 但不同 node_id，疑似重复实体，须人工合并或区分",
                    )
                )
            else:
                seen.setdefault(key, nid)

        # 2) + 3) + 4) 遍历边
        for eid, edge in graph._edges.items():
            src = nodes.get(edge.source_id)
            tgt = nodes.get(edge.target_id)
            # dangling_edge
            if src is None or tgt is None:
                reports.append(
                    self._make(
                        CONFLICT_DANGLING_EDGE,
                        "edge",
                        edge.source_id,
                        edge.target_id,
                        f"边 {eid!r}（{edge.relation_type}）起/止节点缺失（dangling）",
                    )
                )
                continue
            # type_mismatch：复核 add_edge 的约束（理论上不会触发，作为冗余护栏）
            spec = RELATIONSHIP_SPECS.get(edge.relation_type)
            if spec is not None:
                if (
                    src.entity_type != spec.from_entity.value
                    or tgt.entity_type != spec.to_entity.value
                ):
                    reports.append(
                        self._make(
                            CONFLICT_TYPE_MISMATCH,
                            "edge",
                            edge.source_id,
                            edge.target_id,
                            f"边 {eid!r}（{edge.relation_type}）实体类型约束不符："
                            f"{src.entity_type}→{tgt.entity_type}",
                        )
                    )
            # pending_build_edge：生产类关系引用待建骨架节点
            if edge.relation_type in _PRODUCTION_RELATIONS:
                if src.pending_build or tgt.pending_build:
                    reports.append(
                        self._make(
                            CONFLICT_PENDING_BUILD_EDGE,
                            "edge",
                            edge.source_id,
                            edge.target_id,
                            f"生产类关系 {edge.relation_type!r} 引用 pending_build 节点"
                            f"（{src.node_id if src.pending_build else tgt.node_id}），"
                            f"待建骨架禁止参与工程判定，须人工补全后启用",
                        )
                    )
        return reports

    @staticmethod
    def _make(
        ctype: str, scope: str, a: str, b: str, detail: str
    ) -> GraphConflictReport:
        cid = f"GCFL-{abs(hash((ctype, a, b))) % 10**10:010d}"
        return GraphConflictReport(
            conflict_id=cid,
            scope=scope,
            conflict_type=ctype,
            entity_a=a,
            entity_b=b,
            detail=detail,
            review_required=True,
        )


__all__ = [
    "CONFLICT_DUPLICATE_NODE",
    "CONFLICT_DANGLING_EDGE",
    "CONFLICT_PENDING_BUILD_EDGE",
    "CONFLICT_TYPE_MISMATCH",
    "GraphConflictReport",
    "KnowledgeGraphConflictDetector",
]
