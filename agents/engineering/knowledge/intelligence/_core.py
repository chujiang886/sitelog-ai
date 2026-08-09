"""Knowledge Intelligence Layer — 共享只读工具（Phase 3.3 Sprint 3.3.9）。

仅依赖 connector.KnowledgeItem 与 source_ref_validator，**不** import repository，
避免循环依赖。repository 单向 import 本包。
"""

from __future__ import annotations

import json
from typing import Any

from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.thresholds.source_ref_validator import compute_content_hash

# 13 核心字段（与 connector.KnowledgeItem.CORE_FIELD_COUNT 对齐）。
CORE_FIELD_NAMES: tuple[str, ...] = (
    "knowledge_id",
    "knowledge_type",
    "parent_knowledge_id",
    "title",
    "content",
    "source",
    "author",
    "domain",
    "content_hash",
    "validation_status",
    "linked_entities",
    "created_at",
    "updated_at",
)


def canonical_key(item: KnowledgeItem) -> str:
    """对 13 核心字段（排除时间戳与哈希本身）规范化后求 sha256。

    与 repository._canonical_core 同源算法；本地实现以避免 intelligence→repository
    循环 import。用于重复检测（内容相同 → key 相同）。
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
    return compute_content_hash(json.dumps(core, ensure_ascii=False, sort_keys=True))


def is_filled(value: Any) -> bool:
    """字段是否已填：非空字符串且非 pending_verification 占位。"""
    from agents.engineering.knowledge.connector import PENDING_PLACEHOLDER

    if value is None:
        return False
    if isinstance(value, str):
        return value != "" and value != PENDING_PLACEHOLDER
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return True


def linked_entities_filled(item: KnowledgeItem) -> bool:
    """linked_entities 是否含有效（非占位）实体引用。"""
    from agents.engineering.knowledge.connector import PENDING_PLACEHOLDER

    return any(e and e != PENDING_PLACEHOLDER for e in item.linked_entities)


def shared_entities(a: KnowledgeItem, b: KnowledgeItem) -> list[str]:
    """返回两 item 共同引用的 linked_entities（去重、保序）。"""
    set_b = set(b.linked_entities)
    return [e for e in a.linked_entities if e and e in set_b]
