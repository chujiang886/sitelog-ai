"""Knowledge Repository & Governance Layer（Phase 3.3 Sprint 3.3.8）。

建立 KnowledgeItem 长期存储、查询、版本、审计能力：
- ``KnowledgeEvent`` / ``KnowledgeEventLog``：append-only 审计日志；
- ``KnowledgeRepository``：save() / get() / query() / version() / history()；

版本管理（任务2）：每次 save 生成新版本快照，记录 created_at / updated_at /
content_hash / parent_knowledge_id，确保知识演化可追踪。

审计（任务3）：KnowledgeEventLog 记录 create / update / verify / deprecated；
**明确禁止 approved 事件类型**（红线：AI 不代签 / 不代授权 / 不自动 approved）。

权限保护（任务5）：
- 不修改 verified.json value（Repository 仅读写自身 knowledge_repository.json，
  绝不触碰 verified.json）；
- 不开启 engineering_enabled（safety_invariants_ok 只读断言）；
- 不创建 ReleaseApproval（不写 release_approvals.jsonl）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.knowledge.intelligence.conflict import (
    ConflictReport,
    KnowledgeConflictDetector,
)
from agents.engineering.knowledge.intelligence.quality import (
    KnowledgeQualityAnalyzer,
    KnowledgeQualityReport,
)
from agents.engineering.knowledge.intelligence.relationship import (
    KnowledgeRelationshipEngine,
    RelationshipCandidate,
)
from agents.engineering.thresholds.source_ref_validator import compute_content_hash

REPOSITORY_SCHEMA_VERSION: int = 1
DEFAULT_STORE_FILENAME: str = "knowledge_repository.json"

# 审计事件合法类型（任务3）：create / update / verify / deprecated。
# 注意：**不含 approved**——AI 不代签、不代授权、不自动 approved（红线）。
EVENT_TYPES: tuple[str, ...] = ("create", "update", "verify", "deprecated")
FORBIDDEN_EVENT_TYPE: str = "approved"


@dataclass
class KnowledgeEvent:
    """单条知识审计事件。"""

    event_id: str
    knowledge_id: str
    event_type: str
    actor: str
    timestamp: str
    detail: Optional[str] = None
    version: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "knowledge_id": self.knowledge_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "detail": self.detail,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            knowledge_id=str(data.get("knowledge_id", "")),
            event_type=str(data.get("event_type", "")),
            actor=str(data.get("actor", "system")),
            timestamp=str(data.get("timestamp", "")),
            detail=data.get("detail"),
            version=data.get("version"),
        )


class KnowledgeEventLog:
    """任务3：知识审计日志（append-only）。

    记录 create / update / verify / deprecated；明确拒绝 approved。
    """

    def __init__(self, events: Optional[Sequence[Mapping[str, Any]]] = None) -> None:
        self._events: list[KnowledgeEvent] = [
            e if isinstance(e, KnowledgeEvent) else KnowledgeEvent.from_dict(e)
            for e in (events or [])
        ]

    def record(
        self,
        knowledge_id: str,
        event_type: str,
        *,
        actor: str = "system",
        detail: Optional[str] = None,
        version: Optional[int] = None,
        timestamp: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> KnowledgeEvent:
        """记录一条事件；event_type 不属于合法集合（含 approved）则抛错。"""
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"event_type 必须为 {EVENT_TYPES} 之一；"
                f"'{FORBIDDEN_EVENT_TYPE}' 被红线禁止（AI 不代签/不代授权）"
            )
        ev = KnowledgeEvent(
            event_id=event_id or f"EVT-{abs(hash((knowledge_id, event_type, timestamp))) % 10**12:012d}",
            knowledge_id=knowledge_id,
            event_type=event_type,
            actor=actor,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            detail=detail,
            version=version,
        )
        self._events.append(ev)
        return ev

    def events_for(self, knowledge_id: str) -> list[KnowledgeEvent]:
        return [e for e in self._events if e.knowledge_id == knowledge_id]

    def all_events(self) -> list[KnowledgeEvent]:
        return list(self._events)

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]


def _canonical_core(item: KnowledgeItem) -> str:
    """对 13 核心字段（排除时间戳与哈希本身）做规范化序列化，作为 content_hash 源。

    时间戳变化不影响哈希，确保版本演化只反映真实内容/元数据变更。
    """
    core = {
        "knowledge_id": item.knowledge_id,
        "knowledge_type": item.knowledge_type,
        "parent_knowledge_id": item.parent_knowledge_id,
        "title": item.title,
        "content": item.content,
        "source": item.source,
        "author": item.author,
        "domain": item.domain,
        "validation_status": item.validation_status,
        "linked_entities": sorted(item.linked_entities),
    }
    return json.dumps(core, ensure_ascii=False, sort_keys=True)


class KnowledgeRepository:
    """任务1 + 任务2 + 任务4 + 任务5：KnowledgeItem 长期存储 / 查询 / 版本 / 审计。

    存储后端：knowledge_repository.json（自身专属文件，绝不触碰 verified.json）。
    同步方向：本仓库是 BOIP Knowledge Layer 的落盘层；Obsidian Connector
    （任务4）在验证后将 KnowledgeItem 经 save() 入库。
    """

    def __init__(
        self,
        store_path: Optional[str | Path] = None,
        *,
        event_log: Optional[KnowledgeEventLog] = None,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        self.store_path: Optional[Path] = Path(store_path) if store_path else None
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.event_log = event_log or KnowledgeEventLog()
        self._items: dict[str, dict[str, Any]] = {}
        # 智能层（Phase 3.3.9）：只读分析器实例，无副作用。
        self._quality = KnowledgeQualityAnalyzer()
        self._rel = KnowledgeRelationshipEngine()
        self._conflict = KnowledgeConflictDetector()
        if self.store_path and self.store_path.is_file():
            self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        self._items = dict(data.get("items", {}) or {})
        self.event_log = KnowledgeEventLog(data.get("events", []) or [])

    def _persist(self) -> None:
        if not self.store_path:
            return
        payload = {
            "schema_version": REPOSITORY_SCHEMA_VERSION,
            "store_note": (
                "BOIP Knowledge Repository store (Phase 3.3.8). "
                "Red lines: no verified.json mutation; no engineering_enabled; "
                "no ReleaseApproval; no auto-approved."
            ),
            "items": self._items,
            "events": self.event_log.to_list(),
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 任务1：CRUD + query + version + history
    # ------------------------------------------------------------------ #
    def save(
        self,
        item: KnowledgeItem,
        *,
        actor: str = "system",
        event_type: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> int:
        """持久化一个 KnowledgeItem，返回其新版本号。

        - 新 item → version=1，事件 create；
        - 已存在且内容无变化且未显式指定 event_type → 幂等（返回当前版本，不新增）；
        - 已存在且内容变化 → version+1，事件 update；
        - 显式 event_type（如 verify/deprecated）强制新增版本并记该事件。
        """
        existing = self._items.get(item.knowledge_id)
        now = self._clock()

        # 规范化时间戳与内容哈希。
        new_hash = compute_content_hash(_canonical_core(item))
        item.content_hash = new_hash
        if existing is None:
            created_at = item.created_at or now
            version = 1
            etype: str = event_type or "create"
        else:
            current = existing.get("current", {})
            last_version = int(current.get("_version", len(existing.get("versions", []))) or 0)
            created_at = current.get("created_at") or item.created_at or now

            # 幂等判定：内容无变化且未显式指定事件类型 → 不新增版本。
            identical = (
                event_type is None
                and current.get("content_hash") == new_hash
                and current.get("validation_status") == item.validation_status
                and current.get("parent_knowledge_id") == item.parent_knowledge_id
                and current.get("title") == item.title
                and current.get("content") == item.content
            )
            if identical:
                return int(current.get("_version", 1))
            version = last_version + 1
            etype = event_type or "update"

        item.created_at = created_at
        item.updated_at = now
        snapshot = item.to_dict()
        snapshot["_version"] = version

        versions = list(existing.get("versions", [])) if existing else []
        versions.append(dict(snapshot))
        self._items[item.knowledge_id] = {
            "current": dict(snapshot),
            "versions": versions,
        }
        self.event_log.record(
            item.knowledge_id,
            etype,
            actor=actor,
            detail=detail,
            version=version,
            timestamp=now,
        )
        self._persist()
        return version

    def get(self, knowledge_id: str) -> Optional[KnowledgeItem]:
        entry = self._items.get(knowledge_id)
        if not entry:
            return None
        return KnowledgeItem.from_dict(entry["current"])

    def exists(self, knowledge_id: str) -> bool:
        return knowledge_id in self._items

    def query(
        self,
        *,
        domain: Optional[str] = None,
        validation_status: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        author: Optional[str] = None,
        parent_knowledge_id: Optional[str] = None,
        title_contains: Optional[str] = None,
        knowledge_id_prefix: Optional[str] = None,
    ) -> list[KnowledgeItem]:
        """按多维条件过滤当前版本 KnowledgeItem。"""
        results: list[KnowledgeItem] = [
            KnowledgeItem.from_dict(v["current"]) for v in self._items.values()
        ]
        if domain is not None:
            results = [r for r in results if r.domain == domain]
        if validation_status is not None:
            results = [r for r in results if r.validation_status == validation_status]
        if knowledge_type is not None:
            results = [r for r in results if r.knowledge_type == knowledge_type]
        if author is not None:
            results = [r for r in results if r.author == author]
        if parent_knowledge_id is not None:
            results = [r for r in results if r.parent_knowledge_id == parent_knowledge_id]
        if title_contains is not None:
            results = [r for r in results if title_contains in r.title]
        if knowledge_id_prefix is not None:
            results = [r for r in results if r.knowledge_id.startswith(knowledge_id_prefix)]
        return results

    def version(self, knowledge_id: str) -> list[dict[str, Any]]:
        """返回该 item 的所有版本快照（含 _version）。"""
        entry = self._items.get(knowledge_id)
        if not entry:
            return []
        return [dict(v) for v in entry.get("versions", [])]

    def history(self, knowledge_id: str) -> list[KnowledgeEvent]:
        """返回该 item 的审计事件时间线（按记录顺序）。"""
        return self.event_log.events_for(knowledge_id)

    def item_count(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------ #
    # 任务3：显式审计事件（verify / deprecated），仍禁止 approved
    # ------------------------------------------------------------------ #
    def record_event(
        self,
        knowledge_id: str,
        event_type: str,
        *,
        actor: str = "system",
        detail: Optional[str] = None,
        version: Optional[int] = None,
    ) -> KnowledgeEvent:
        """追加一条审计事件（不改动 item 内容）；approved 被拒绝。"""
        if knowledge_id not in self._items:
            raise KeyError(f"knowledge_id={knowledge_id} 不存在，无法记录事件")
        return self.event_log.record(
            knowledge_id,
            event_type,
            actor=actor,
            detail=detail,
            version=version,
        )

    def verify(
        self,
        knowledge_id: str,
        *,
        actor: str = "system",
        detail: Optional[str] = None,
        new_status: str = "Source_Verified",
    ) -> int:
        """标记 item 进入某 verify 态（默认 Source_Verified），记录 verify 事件。

        注意：仅置 verify 态，**绝不**置 Engineering_Approved（approved 被禁止）。
        """
        item = self.get(knowledge_id)
        if item is None:
            raise KeyError(f"knowledge_id={knowledge_id} 不存在")
        item.validation_status = new_status
        return self.save(item, actor=actor, event_type="verify", detail=detail)

    def deprecate(
        self,
        knowledge_id: str,
        *,
        actor: str = "system",
        detail: Optional[str] = None,
        successor: Optional[str] = None,
    ) -> int:
        """将 item 置 Deprecated，记录 deprecated 事件；可选置 successor 谱系。"""
        item = self.get(knowledge_id)
        if item is None:
            raise KeyError(f"knowledge_id={knowledge_id} 不存在")
        item.validation_status = "Deprecated"
        if successor is not None:
            item.parent_knowledge_id = successor
        return self.save(item, actor=actor, event_type="deprecated", detail=detail)

    # ------------------------------------------------------------------ #
    # 任务4：Knowledge Intelligence Layer 只读集成（Phase 3.3.9）
    # 全部只读：不写 knowledge_repository.json、不记审计事件、不翻 engineering_enabled；
    # 不破坏 save/get/query/version/history/verify/deprecate 任何签名或语义。
    # ------------------------------------------------------------------ #
    def _all_items(self) -> list[KnowledgeItem]:
        """返回当前版本所有 KnowledgeItem（只读快照）。"""
        return [KnowledgeItem.from_dict(v["current"]) for v in self._items.values()]

    def quality_report(self, knowledge_id: str) -> KnowledgeQualityReport:
        """对单条 item 做质量评估（只读，无 save/event）。"""
        item = self.get(knowledge_id)
        if item is None:
            raise KeyError(f"knowledge_id={knowledge_id} 不存在")
        return self._quality.analyze(item, repo=self)

    def find_relationships(self, knowledge_id: str) -> list[RelationshipCandidate]:
        """返回与指定 item 相关的全部候选关系（只读）。"""
        items = self._all_items()
        return [
            c
            for c in self._rel.discover(items)
            if c.source_id == knowledge_id or c.target_id == knowledge_id
        ]

    def detect_conflicts(
        self,
        *,
        knowledge_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> list[ConflictReport]:
        """检测冲突（只读）；review_required 恒定 True。"""
        items = self._all_items()
        if domain is not None:
            items = [i for i in items if i.domain == domain]
        reports = self._conflict.detect(items)
        if knowledge_id is not None:
            reports = [
                r for r in reports if r.item_a == knowledge_id or r.item_b == knowledge_id
            ]
        return reports

    def analyze(self, knowledge_id: Optional[str] = None) -> dict[str, Any]:
        """聚合单条 item 的智能视图（quality + relationships + conflicts，只读快照）。

        - 指定 knowledge_id：返回该 item 的质量/关系/冲突视图；
        - 不指定：返回仓库级聚合（条目数 / 冲突总数 / 关系总数）。
        """
        if knowledge_id is not None:
            item = self.get(knowledge_id)
            if item is None:
                raise KeyError(f"knowledge_id={knowledge_id} 不存在")
            return {
                "knowledge_id": knowledge_id,
                "quality": self.quality_report(knowledge_id),
                "relationships": self.find_relationships(knowledge_id),
                "conflicts": self.detect_conflicts(knowledge_id=knowledge_id),
            }
        return {
            "item_count": self.item_count(),
            "conflicts_total": len(self.detect_conflicts()),
            "relationships_total": len(self._rel.discover(self._all_items())),
        }

    # ------------------------------------------------------------------ #
    # 任务5：权限保护（只读断言，零写入 verified.json / 不开启 enabled）
    # ------------------------------------------------------------------ #
    @staticmethod
    def safety_invariants_ok() -> bool:
        """安全护栏只读断言：engineering_enabled 必须保持 False。"""
        return load_engineering_enabled() is False


__all__ = [
    "REPOSITORY_SCHEMA_VERSION",
    "DEFAULT_STORE_FILENAME",
    "EVENT_TYPES",
    "FORBIDDEN_EVENT_TYPE",
    "KnowledgeEvent",
    "KnowledgeEventLog",
    "KnowledgeRepository",
    "KnowledgeQualityAnalyzer",
    "KnowledgeQualityReport",
    "KnowledgeRelationshipEngine",
    "RelationshipCandidate",
    "KnowledgeConflictDetector",
    "ConflictReport",
]
