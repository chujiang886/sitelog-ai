"""Engineering Context Builder（Phase 3.4 Sprint 3.4.4 任务3）。

把经 Consumption Guard 过滤后的知识装配为 Engineering Agent 的上下文：
authoritative 知识可作权威依据；auxiliary 知识仅辅助且须标 pending_verification；
blocked 知识不进入上下文。

本模块只做结构装配，不判定知识态、不读写激活态，也不产生任何业务数值。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.engineering.knowledge.connector import KnowledgeItem


@dataclass
class RAGContext:
    """RAG 流程输出的工程上下文（已分区）。"""

    query: str
    retrieved: list[KnowledgeItem] = field(default_factory=list)
    authoritative: list[KnowledgeItem] = field(default_factory=list)
    auxiliary: list[KnowledgeItem] = field(default_factory=list)
    blocked: list[KnowledgeItem] = field(default_factory=list)
    decision_allowed: bool = False

    def to_agent_context(self) -> dict[str, Any]:
        """装配 Engineering Agent 可直接消费的上下文结构。"""

        return {
            "query": self.query,
            "authoritative_knowledge": [self._item_view(i) for i in self.authoritative],
            "auxiliary_knowledge": [
                {**self._item_view(i), "requires_pending_verification": True}
                for i in self.auxiliary
            ],
            "blocked_knowledge_ids": [i.knowledge_id for i in self.blocked],
            "decision_allowed": self.decision_allowed,
        }

    @staticmethod
    def _item_view(item: KnowledgeItem) -> dict[str, Any]:
        return {
            "knowledge_id": item.knowledge_id,
            "title": item.title,
            "domain": item.domain,
            "validation_status": item.validation_status,
        }


__all__ = ["RAGContext"]
