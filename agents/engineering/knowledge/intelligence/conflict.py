"""Knowledge Conflict Detector（Phase 3.3 Sprint 3.3.9, Task 3）。

KnowledgeConflictDetector.detect(items) -> list[ConflictReport]

同 domain 内检测三类冲突：
- parameter : 共享 linked_entities（同一工程实体）但 content 不同。
- source    : 共享 linked_entities 但引用 source（source_id）不同。
- status    : 某 item 为 Deprecated，但仍有他 item 通过 parent_knowledge_id /
              linked_entities 引用它（悬垂引用）。

红线约束：
- review_required 恒定 True，**绝不**自动解决冲突。
- detect() 不写盘、不调 deprecate/verify、不输出任何解决结论；
  冲突仅进入"待人工复核"队列（AI 不代专家审核）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.intelligence._core import shared_entities

CONFLICT_PARAMETER: str = "parameter"
CONFLICT_SOURCE: str = "source"
CONFLICT_STATUS: str = "status"

_VALID_TYPES: tuple[str, ...] = (CONFLICT_PARAMETER, CONFLICT_SOURCE, CONFLICT_STATUS)


@dataclass
class ConflictReport:
    """一条冲突报告；review_required 恒定 True（永不自动解决）。"""

    conflict_id: str
    domain: str
    conflict_type: str
    item_a: str
    item_b: str
    detail: str
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "domain": self.domain,
            "conflict_type": self.conflict_type,
            "item_a": self.item_a,
            "item_b": self.item_b,
            "detail": self.detail,
            "review_required": self.review_required,
        }


class KnowledgeConflictDetector:
    """Task 3：知识冲突检测（只读，review_required 恒 True）。"""

    def detect(self, items: Sequence[KnowledgeItem]) -> list[ConflictReport]:
        items = [it for it in items if it.domain and it.domain != PENDING_PLACEHOLDER]
        reports: list[ConflictReport] = []
        index = {it.knowledge_id: it for it in items}

        n = len(items)
        for i in range(n):
            a = items[i]
            for j in range(i + 1, n):
                b = items[j]
                if a.knowledge_id == b.knowledge_id:
                    continue
                if a.domain != b.domain:
                    continue
                shared = shared_entities(a, b)
                if not shared:
                    continue
                # parameter：同实体但 content 不同
                if a.content != b.content:
                    reports.append(
                        self._make(
                            CONFLICT_PARAMETER,
                            a,
                            b,
                            f"同 domain={a.domain!r} 共享实体 {shared} 但 content 不同，参数可能冲突",
                        )
                    )
                # source：同实体但引用 source 不同
                if a.source and b.source and a.source != b.source and a.source != PENDING_PLACEHOLDER and b.source != PENDING_PLACEHOLDER:
                    reports.append(
                        self._make(
                            CONFLICT_SOURCE,
                            a,
                            b,
                            f"同 domain={a.domain!r} 共享实体 {shared} 但引用 source 不同（{a.source!r} vs {b.source!r}）",
                        )
                    )

        # status：Deprecated 被引用（悬垂引用）
        for kid, it in index.items():
            if it.validation_status != "Deprecated":
                continue
            for other in items:
                if other.knowledge_id == kid:
                    continue
                referenced = (
                    other.parent_knowledge_id == kid
                    or kid in other.linked_entities
                )
                if referenced:
                    reports.append(
                        self._make(
                            CONFLICT_STATUS,
                            it,
                            other,
                            f"item {kid!r} 已 Deprecated，但仍被 {other.knowledge_id!r} 引用（悬垂引用）",
                        )
                    )
        return reports

    @staticmethod
    def _make(
        ctype: str,
        a: KnowledgeItem,
        b: KnowledgeItem,
        detail: str,
    ) -> ConflictReport:
        cid = f"CFL-{abs(hash((ctype, a.knowledge_id, b.knowledge_id))) % 10**10:010d}"
        return ConflictReport(
            conflict_id=cid,
            domain=a.domain,
            conflict_type=ctype,
            item_a=a.knowledge_id,
            item_b=b.knowledge_id,
            detail=detail,
            review_required=True,
        )


__all__ = [
    "CONFLICT_PARAMETER",
    "CONFLICT_SOURCE",
    "CONFLICT_STATUS",
    "ConflictReport",
    "KnowledgeConflictDetector",
]
