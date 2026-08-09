"""Engineering RAG 接入包（Phase 3.4 Sprint 3.4.4 任务3）。

Retriever → Consumption Guard → ContextBuilder → Engineering Agent。

检索出的知识必须经 ``EngineeringKnowledgeGuard`` 过滤后才进入工程上下文；
本包不判定知识态、不读写激活态、不产出任何业务数值。
"""

from __future__ import annotations

from agents.engineering.knowledge.rag.context_builder import RAGContext
from agents.engineering.knowledge.rag.pipeline import RAGPipeline
from agents.engineering.knowledge.rag.retriever import KnowledgeRetriever, RetrievalResult

__all__ = [
    "KnowledgeRetriever",
    "RetrievalResult",
    "RAGContext",
    "RAGPipeline",
]
