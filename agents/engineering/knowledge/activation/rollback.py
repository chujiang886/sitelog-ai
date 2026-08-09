"""Knowledge Rollback Policy（Phase 3.4 Sprint 3.4.1, Task 4）。

失效回滚链：有效 KnowledgeItem → deprecate(successor=) → Deprecated → Successor
（承载取代内容）→ Replacement 生效。

要点（与设计文档 phase3.4.0 §7 对齐）：
- 复用 Repository.deprecate(successor=)（3.3.8 已实现）作为回滚主路径；
- 回滚**不删除**历史：旧 item 保留全部版本快照与审计事件，仅置 Deprecated + 链接 successor；
- successor 在 Repository 中存放于被废弃 item 的 parent_knowledge_id（见 repository.deprecate）。
- 本类只做治理编排，**绝不**翻转 engineering_enabled、不创建 ReleaseApproval、不修改 verified.json。
"""

from __future__ import annotations

from typing import Optional

from agents.engineering.knowledge.connector import PENDING_PLACEHOLDER
from agents.engineering.knowledge.repository import KnowledgeRepository

DEPRECATED_STATUS: str = "Deprecated"


class KnowledgeRollbackPolicy:
    """Task 4：知识回滚策略（仅治理编排，不删历史）。"""

    def deprecate(
        self,
        repository: KnowledgeRepository,
        knowledge_id: str,
        *,
        successor: Optional[str] = None,
        actor: str = "rollback",
        detail: Optional[str] = None,
    ) -> int:
        """将被废弃 item 置 Deprecated 并（可选）链接 successor；保留历史。"""
        return repository.deprecate(
            knowledge_id,
            successor=successor,
            actor=actor,
            detail=detail,
        )

    def successor_of(
        self,
        repository: KnowledgeRepository,
        knowledge_id: str,
    ) -> Optional[str]:
        """返回被废弃 item 的 successor（仅对 Deprecated 有效）。"""
        item = repository.get(knowledge_id)
        if item is None or item.validation_status != DEPRECATED_STATUS:
            return None
        s = item.parent_knowledge_id
        return s if s and s != PENDING_PLACEHOLDER else None

    def build_replacement_chain(
        self,
        repository: KnowledgeRepository,
        deprecated_id: str,
    ) -> list[str]:
        """构建 Deprecated → successor（一跳）替换链。不递归以避免回环。"""
        chain = [deprecated_id]
        succ = self.successor_of(repository, deprecated_id)
        if succ:
            chain.append(succ)
        return chain

    def is_replacement_available(
        self,
        repository: KnowledgeRepository,
        deprecated_id: str,
    ) -> bool:
        """是否存在可用的 successor（回滚就绪判据之一）。"""
        return self.successor_of(repository, deprecated_id) is not None

    def history_preserved(
        self,
        repository: KnowledgeRepository,
        knowledge_id: str,
    ) -> bool:
        """回滚后历史是否保留：item 仍存在且至少有一条版本快照。"""
        if not repository.exists(knowledge_id):
            return False
        return len(repository.version(knowledge_id)) >= 1


__all__ = [
    "DEPRECATED_STATUS",
    "KnowledgeRollbackPolicy",
]
