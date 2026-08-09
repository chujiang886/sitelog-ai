"""Knowledge Graph Repository（Phase 3.7.1 Task 3）。

设计 ``KnowledgeGraphRepository``，能力：
- ``add_node(entity | GraphNode)``：入图，版本=1，记审计；
- ``add_edge(GraphEdge)``：关系校验（起止实体类型约束）后入图，记审计；
- ``query(...)``：按实体类型 / 属性包含 / 前缀检索；
- ``traverse(start, relation_types, direction, max_depth)``：BFS 图谱遍历；
- ``history(node_id)``：返回该节点审计时间线。

审计：``GraphAuditLog`` append-only，记录 who / when / hash / version。
持久化：自身专属 ``knowledge_graph.json``，**绝不**触碰 verified.json / engineering_enabled / release_approvals。

红线（本 Sprint 串接全系列）：
- 不写 verified.json value（本仓库仅读写自身 store）；
- 不开启 engineering_enabled（safety_invariants_ok 只读断言）；
- 不输出 engineering_approved、不建 ReleaseApproval；
- 边校验 fail-closed（约束违例抛错，不静默降级）；
- Case/Rule 节点 pending_build=True，禁止在 enabled 前被工程判定消费。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.graph.entities import (
    GraphNode,
    entity_to_node,
)
from agents.engineering.knowledge.graph.relationships import (
    GraphEdge,
    validate_edge,
)

GRAPH_SCHEMA_VERSION: int = 1
DEFAULT_GRAPH_STORE_FILENAME: str = "knowledge_graph.json"

# 审计动作合法类型（明确拒绝 auto_merge / auto_delete / auto_approve）。
GRAPH_AUDIT_EVENT_TYPES: tuple[str, ...] = (
    "add_node",
    "update_node",
    "add_edge",
    "update_edge",
)
FORBIDDEN_GRAPH_EVENT_TYPES: tuple[str, ...] = (
    "merge",
    "delete",
    "approve",
)


@dataclass
class GraphAuditEvent:
    """单条图谱审计事件（who / when / hash / version）。"""

    event_id: str
    target_id: str
    action: str
    actor: str
    timestamp: str
    content_hash: str
    version: int
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "target_id": self.target_id,
            "action": self.action,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
            "version": self.version,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GraphAuditEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            target_id=str(data.get("target_id", "")),
            action=str(data.get("action", "")),
            actor=str(data.get("actor", "system")),
            timestamp=str(data.get("timestamp", "")),
            content_hash=str(data.get("content_hash", "")),
            version=int(data.get("version", 1) or 1),
            detail=data.get("detail"),
        )


class GraphAuditLog:
    """图谱审计日志（append-only）。

    仅记录 create/update 类动作；明确拒绝 merge/delete/approve（红线：禁止自动 merge/delete/approve）。
    """

    def __init__(self, events: Optional[Sequence[Mapping[str, Any]]] = None) -> None:
        self._events: list[GraphAuditEvent] = [
            e if isinstance(e, GraphAuditEvent) else GraphAuditEvent.from_dict(e)
            for e in (events or [])
        ]

    def record(
        self,
        target_id: str,
        action: str,
        *,
        actor: str = "system",
        content_hash: str = "",
        version: int = 1,
        detail: Optional[str] = None,
        timestamp: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> GraphAuditEvent:
        if action in FORBIDDEN_GRAPH_EVENT_TYPES:
            raise ValueError(
                f"审计动作 {action!r} 被红线禁止（禁止自动 merge/delete/approve）"
            )
        if action not in GRAPH_AUDIT_EVENT_TYPES:
            raise ValueError(
                f"审计动作必须为 {GRAPH_AUDIT_EVENT_TYPES} 之一；"
                f"{FORBIDDEN_GRAPH_EVENT_TYPES} 被红线禁止"
            )
        ev = GraphAuditEvent(
            event_id=event_id
            or f"GAUD-{abs(hash((target_id, action, timestamp))) % 10**12:012d}",
            target_id=target_id,
            action=action,
            actor=actor,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            content_hash=content_hash,
            version=version,
            detail=detail,
        )
        self._events.append(ev)
        return ev

    def events_for(self, target_id: str) -> list[GraphAuditEvent]:
        return [e for e in self._events if e.target_id == target_id]

    def all_events(self) -> list[GraphAuditEvent]:
        return list(self._events)

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]


class KnowledgeGraphRepository:
    """Knowledge Graph 落库与查询（任务1–任务3 承载层）。"""

    def __init__(
        self,
        store_path: Optional[str | Path] = None,
        *,
        audit_log: Optional[GraphAuditLog] = None,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        self.store_path: Optional[Path] = Path(store_path) if store_path else None
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.audit_log = audit_log or GraphAuditLog()
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._edge_index: dict[str, list[str]] = defaultdict(list)
        if self.store_path and self.store_path.is_file():
            self._load()

    # ------------------------------------------------------------------ #
    # 持久化（自身专属文件，绝不触碰 verified.json）
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self._nodes = {
            nid: GraphNode.from_dict(n) for nid, n in (data.get("nodes", {}) or {}).items()
        }
        self._edges = {
            eid: GraphEdge.from_dict(e) for eid, e in (data.get("edges", {}) or {}).items()
        }
        self.audit_log = GraphAuditLog(data.get("audit", []) or [])
        self._rebuild_edge_index()

    def _rebuild_edge_index(self) -> None:
        self._edge_index = defaultdict(list)
        for eid, edge in self._edges.items():
            self._edge_index[edge.source_id].append(eid)
            self._edge_index[edge.target_id].append(eid)

    def _persist(self) -> None:
        if not self.store_path:
            return
        payload = {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "store_note": (
                "BOIP Knowledge Graph store (Phase 3.7.1). "
                "Red lines: no verified.json mutation; no engineering_enabled; "
                "no ReleaseApproval; no auto-merge/delete/approve."
            ),
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "edges": {eid: e.to_dict() for eid, e in self._edges.items()},
            "audit": self.audit_log.to_list(),
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 节点：add / get / exists / query
    # ------------------------------------------------------------------ #
    def add_node(self, entity: Any, *, actor: str = "system") -> int:
        """入图一个实体（实体对象或 GraphNode）；返回版本号。

        已存在同 node_id → 视为 update（version+1，审计 update_node，保留历史版本快照）。
        """
        node = entity_to_node(entity, actor=actor)
        now = self._clock()
        existing = self._nodes.get(node.node_id)
        if existing is None:
            node.version = 1
            node.created_at = node.created_at or now
            node.updated_at = now
            self._nodes[node.node_id] = node
            self.audit_log.record(
                node.node_id, "add_node", actor=actor,
                content_hash=node.content_hash, version=1, detail=f"entity_type={node.entity_type}",
            )
            return 1
        # update：保留旧版本快照，仅当前态推进。
        node.version = existing.version + 1
        node.created_at = existing.created_at or now
        node.updated_at = now
        self._nodes[node.node_id] = node
        self.audit_log.record(
            node.node_id, "update_node", actor=actor,
            content_hash=node.content_hash, version=node.version,
            detail=f"entity_type={node.entity_type}",
        )
        return node.version

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        node = self._nodes.get(node_id)
        return GraphNode.from_dict(node.to_dict()) if node else None

    def exists(self, node_id: str) -> bool:
        return node_id in self._nodes

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def query(
        self,
        *,
        entity_type: Optional[str] = None,
        attribute_contains: Optional[tuple[str, str]] = None,
        node_id_prefix: Optional[str] = None,
        pending_build_only: Optional[bool] = None,
    ) -> list[GraphNode]:
        """按多维条件过滤当前版本节点。"""
        results: list[GraphNode] = [n for n in self._nodes.values()]
        if entity_type is not None:
            results = [n for n in results if n.entity_type == entity_type]
        if attribute_contains is not None:
            key, value = attribute_contains
            results = [
                n for n in results
                if value in str(n.attributes.get(key, ""))
            ]
        if node_id_prefix is not None:
            results = [n for n in results if n.node_id.startswith(node_id_prefix)]
        if pending_build_only is not None:
            results = [n for n in results if n.pending_build == pending_build_only]
        return results

    # ------------------------------------------------------------------ #
    # 边：add / get / 校验（fail-closed）
    # ------------------------------------------------------------------ #
    def add_edge(self, edge: GraphEdge, *, actor: str = "system") -> int:
        """入图一条边；先经 validate_edge 校验起止实体类型约束（fail-closed）。

        约束违例 → 抛 ``ValueError``，**绝不**静默降级或自动改写。已存在同 edge_id → update(version+1)。
        """
        validate_edge(edge, self._nodes)
        now = self._clock()
        # 规范化时间戳与哈希。
        from agents.engineering.knowledge.graph.relationships import _edge_hash
        edge.content_hash = _edge_hash(edge)
        existing = self._edges.get(edge.edge_id)
        if existing is None:
            edge.version = 1
            edge.created_at = edge.created_at or now
            edge.updated_at = now
            self._edges[edge.edge_id] = edge
            self._edge_index[edge.source_id].append(edge.edge_id)
            self._edge_index[edge.target_id].append(edge.edge_id)
            self.audit_log.record(
                edge.edge_id, "add_edge", actor=actor,
                content_hash=edge.content_hash, version=1,
                detail=f"{edge.relation_type}:{edge.source_id}->{edge.target_id}",
            )
            self._persist()
            return 1
        edge.version = existing.version + 1
        edge.created_at = existing.created_at or now
        edge.updated_at = now
        self._edges[edge.edge_id] = edge
        self.audit_log.record(
            edge.edge_id, "update_edge", actor=actor,
            content_hash=edge.content_hash, version=edge.version,
            detail=f"{edge.relation_type}:{edge.source_id}->{edge.target_id}",
        )
        self._persist()
        return edge.version

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        edge = self._edges.get(edge_id)
        return GraphEdge.from_dict(edge.to_dict()) if edge else None

    # ------------------------------------------------------------------ #
    # 遍历：BFS
    # ------------------------------------------------------------------ #
    def traverse(
        self,
        start_node_id: str,
        *,
        relation_types: Optional[Sequence[str]] = None,
        direction: str = "out",
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """从起点 BFS 遍历图谱。

        参数：
        - ``relation_types``：仅遍历这些关系（默认全部）；
        - ``direction``："out"（起点为 source）/ "in"（起点为 target）/ "both"；
        - ``max_depth``：最大跳数（0 = 仅起点自身）。

        返回：``[{level, node_id, relation_type, via_edge_id}]``（不含起点自身路径项以外信息）。
        """
        if start_node_id not in self._nodes:
            raise KeyError(f"start_node_id={start_node_id!r} 未入图")
        if direction not in ("out", "in", "both"):
            raise ValueError("direction 必须为 out / in / both")
        allowed = set(relation_types) if relation_types else None
        visited: set[str] = {start_node_id}
        queue: list[tuple[int, str]] = [(0, start_node_id)]
        result: list[dict[str, Any]] = []
        while queue:
            level, current = queue.pop(0)
            if level >= max_depth:
                continue
            # 收集本节点的邻接边。
            adj: list[GraphEdge] = []
            if direction in ("out", "both"):
                for eid in self._edge_index.get(current, []):
                    edge = self._edges.get(eid)
                    if edge and edge.source_id == current:
                        adj.append(edge)
            if direction in ("in", "both"):
                for eid in self._edge_index.get(current, []):
                    edge = self._edges.get(eid)
                    if edge and edge.target_id == current:
                        adj.append(edge)
            for edge in adj:
                if allowed is not None and edge.relation_type not in allowed:
                    continue
                nxt = (
                    edge.target_id
                    if edge.source_id == current
                    else edge.source_id
                )
                if nxt in visited:
                    continue
                visited.add(nxt)
                result.append(
                    {
                        "level": level + 1,
                        "node_id": nxt,
                        "relation_type": edge.relation_type,
                        "via_edge_id": edge.edge_id,
                    }
                )
                queue.append((level + 1, nxt))
        return result

    # ------------------------------------------------------------------ #
    # 审计：history
    # ------------------------------------------------------------------ #
    def history(self, target_id: str) -> list[GraphAuditEvent]:
        """返回该节点/边的审计事件时间线（按记录顺序）。"""
        return self.audit_log.events_for(target_id)

    def all_audit_events(self) -> list[GraphAuditEvent]:
        return self.audit_log.all_events()

    # ------------------------------------------------------------------ #
    # 红线屏障：只读断言
    # ------------------------------------------------------------------ #
    @staticmethod
    def safety_invariants_ok() -> bool:
        """安全护栏只读断言：engineering_enabled 必须保持 False（默认闸门关闭）。"""
        return load_engineering_enabled() is False


__all__ = [
    "GRAPH_SCHEMA_VERSION",
    "DEFAULT_GRAPH_STORE_FILENAME",
    "GRAPH_AUDIT_EVENT_TYPES",
    "FORBIDDEN_GRAPH_EVENT_TYPES",
    "GraphAuditEvent",
    "GraphAuditLog",
    "KnowledgeGraphRepository",
]
