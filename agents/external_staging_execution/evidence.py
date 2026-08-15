"""Phase 3.9.11 —— 执行证据链（Tasks 22-24）。

证据类型仅限 ``plan_only`` / ``contract_test`` / ``pending``：**绝不**包含真实连接/
真实执行证据（Track B 资源 PENDING）。每条证据自动计算 SHA-256（基于内容，剔除 hash
自身），链哈希由各条证据 hash 串联。``contains_secret`` 恒为 False。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionEvidenceItem:
    """单条执行证据。"""

    evidence_id: str
    step_kind: str
    evidence_type: str  # "plan_only" | "contract_test" | "pending"
    environment: str
    actor: str
    verification_status: str
    detail: str
    contains_secret: bool = False
    hash: str = ""

    def _body(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "hash"}

    def compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self._body(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


class ExecutionEvidenceChain:
    """执行证据链（plan/contract/pending，无真实执行证据）。"""

    def __init__(self, items: list[ExecutionEvidenceItem] | None = None) -> None:
        self.items: list[ExecutionEvidenceItem] = list(items or [])

    def add(self, item: ExecutionEvidenceItem) -> None:
        item.hash = item.compute_hash()
        self.items.append(item)

    def summary(self) -> dict[str, Any]:
        by_type = dict(Counter(i.evidence_type for i in self.items))
        return {
            "count": len(self.items),
            "by_type": by_type,
            "none_contains_secret": all(not i.contains_secret for i in self.items),
            "all_scope_external_staging": all(
                i.environment == "external_staging" for i in self.items
            ),
        }

    def chain_hash(self) -> str:
        h = hashlib.sha256()
        for i in self.items:
            h.update(i.hash.encode("utf-8"))
        return h.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.__dict__ for i in self.items],
            "summary": self.summary(),
            "chain_hash": self.chain_hash(),
        }


__all__ = ["ExecutionEvidenceItem", "ExecutionEvidenceChain"]
