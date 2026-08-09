"""Knowledge Relationship Engine（Phase 3.3 Sprint 3.3.9, Task 2）。

KnowledgeRelationshipEngine.discover(items) -> list[RelationshipCandidate]

发现四类候选关系（**仅产生 candidate，禁止 approve / merge / delete**）：
- parent_child        : item.parent_knowledge_id 指向另一 item。
- related             : 同 domain 且 linked_entities 交集 >= 1。
- duplicate_candidate : 两 item 内容规范 key 相同（疑似重复）。
- conflict_candidate  : 同 domain + 共享实体但 content 不同（转交 ConflictDetector 复核）。

discover() 为**纯函数**：只读 items 列表、返回候选；不写盘、不调 save/deprecate、
不记审计事件（红线：禁止自动 merge/delete/approve）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.intelligence._core import shared_entities

REL_PARENT_CHILD: str = "parent_child"
REL_RELATED: str = "related"
REL_DUPLICATE: str = "duplicate_candidate"
REL_CONFLICT: str = "conflict_candidate"

_VALID_TYPES: tuple[str, ...] = (
    REL_PARENT_CHILD,
    REL_RELATED,
    REL_DUPLICATE,
    REL_CONFLICT,
)


@dataclass
class RelationshipCandidate:
    """一条候选关系（只读发现产物，不代表已确认/已合并）。"""

    relationship_type: str
    source_id: str
    target_id: str
    confidence: float
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_type": self.relationship_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "confidence": self.confidence,
            "basis": self.basis,
        }


class KnowledgeRelationshipEngine:
    """Task 2：知识关系发现（纯函数，只读）。"""

    def discover(self, items: Sequence[KnowledgeItem]) -> list[RelationshipCandidate]:
        items = list(items)
        id_index = {it.knowledge_id: it for it in items if it.knowledge_id}
        seen: set[tuple[str, str, str]] = set()
        found: list[RelationshipCandidate] = []

        def add(rtype: str, a: str, b: str, conf: float, basis: str) -> None:
            key = (rtype, a, b)
            if key in seen or a == b:
                return
            seen.add(key)
            found.append(RelationshipCandidate(rtype, a, b, conf, basis))

        # 1) parent_child
        for it in items:
            parent = it.parent_knowledge_id
            if parent and parent != PENDING_PLACEHOLDER and parent in id_index:
                add(REL_PARENT_CHILD, it.knowledge_id, parent, 1.0, "parent_knowledge_id 指向已存在 item")

        # 2) 成对：related / duplicate / conflict
        n = len(items)
        for i in range(n):
            a = items[i]
            for j in range(i + 1, n):
                b = items[j]
                if a.knowledge_id == b.knowledge_id:
                    continue
                # duplicate_candidate：内容相同（content 一致 → 疑似重复）
                if a.content == b.content:
                    add(REL_DUPLICATE, a.knowledge_id, b.knowledge_id, 0.9, "content 相同，疑似重复")
                    continue
                # 同 domain 才进一步判 related / conflict
                if a.domain and a.domain == b.domain and a.domain != PENDING_PLACEHOLDER:
                    shared = shared_entities(a, b)
                    if shared:
                        add(
                            REL_RELATED,
                            a.knowledge_id,
                            b.knowledge_id,
                            0.6,
                            f"同 domain 且共享实体 {shared}",
                        )
                        if a.content != b.content:
                            add(
                                REL_CONFLICT,
                                a.knowledge_id,
                                b.knowledge_id,
                                0.7,
                                f"同 domain 共享实体 {shared} 但 content 不同，需冲突复核",
                            )
        return found


__all__ = [
    "REL_PARENT_CHILD",
    "REL_RELATED",
    "REL_DUPLICATE",
    "REL_CONFLICT",
    "RelationshipCandidate",
    "KnowledgeRelationshipEngine",
]
