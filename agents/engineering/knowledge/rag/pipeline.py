"""RAG Pipeline（Phase 3.4 Sprint 3.4.4 任务3）。

流程：Retriever → Consumption Guard → Context Builder → Engineering Agent。

- Retriever 从语料检索候选 KnowledgeItem；
- Consumption Guard 对每条候选调用 ``EngineeringKnowledgeGuard
  .guard_engineering_computation_input``（统一闸门决策 + 消费策略分级），分区
  authoritative / auxiliary / blocked；
- ContextBuilder 装配 Engineering Agent 上下文（authoritative 权威、auxiliary 仅
  辅助须 pending、blocked 不进入）；
- 顶层红线不变量（``engineering_enabled`` 必须 False）由 guard 内部强制。

红线：不开启 engineering_enabled / 不输出 engineering_approved / 不建
ReleaseApproval / 不修改 verified.json / AI 不代专家授权；审计仅记
knowledge_consumed / knowledge_blocked，显式拒绝 approved。
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from agents.engineering.gate.unified_activation_gate import UnifiedActivationDecision
from agents.engineering.knowledge.activation.consumer_guard import (
    EngineeringKnowledgeGuard,
)
from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.knowledge.rag.context_builder import RAGContext
from agents.engineering.knowledge.rag.retriever import KnowledgeRetriever, RetrievalResult


class RAGPipeline:
    """Retriever → Consumption Guard → ContextBuilder 编排器。"""

    def __init__(
        self,
        *,
        retriever: Optional[KnowledgeRetriever] = None,
        guard: Optional[EngineeringKnowledgeGuard] = None,
        decision_provider: Optional[Callable[[KnowledgeItem], UnifiedActivationDecision]] = None,
    ) -> None:
        self._retriever = retriever or KnowledgeRetriever()
        self._guard = guard or EngineeringKnowledgeGuard()
        # 可选：为每条 item 定制决策（缺省使用 run() 传入的共享 decision）。
        self._decision_provider = decision_provider

    @property
    def guard(self) -> EngineeringKnowledgeGuard:
        return self._guard

    def run(
        self,
        query: str,
        corpus: Sequence[KnowledgeItem],
        decision: UnifiedActivationDecision,
        *,
        top_k: Optional[int] = None,
    ) -> RAGContext:
        """执行一次 RAG 检索 + 消费过滤 + 上下文装配。"""

        retrieval: RetrievalResult = self._retriever.retrieve(query, corpus, top_k=top_k)
        ctx = RAGContext(
            query=query,
            retrieved=retrieval.items(),
            decision_allowed=bool(decision.allowed),
        )
        for item in retrieval.items():
            # 决策提供者可为每条 item 定制；缺省使用共享 decision。
            dec = self._decision_provider(item) if self._decision_provider else decision
            res = self._guard.guard_engineering_computation_input(item, dec)
            if not res.permitted:
                ctx.blocked.append(item)
            elif res.as_authoritative:
                ctx.authoritative.append(item)
            else:
                ctx.auxiliary.append(item)
        return ctx


__all__ = ["RAGPipeline"]
