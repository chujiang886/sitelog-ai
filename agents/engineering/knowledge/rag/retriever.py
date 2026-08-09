"""Knowledge Retriever（Phase 3.4 Sprint 3.4.4 任务3）。

从 KnowledgeItem 语料中按查询检索候选条目，供后续 Consumption Guard 过滤。

设计：
- 默认使用轻量确定性词面打分器（领域 / 标题 / 正文 / linked_entities 的 Jaccard
  重叠 + 领域精确匹配加权），不依赖外部向量库、不产生网络请求；
- 可选注入 ``embedder``（``callable: str -> list[float]``）做余弦相似度检索，
  便于接入真实 embedding 服务而不改流程结构。

检索结果仅输出候选集；是否进入工程上下文由 Consumption Guard 决定（本模块不判
定知识态、不读写激活态）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from agents.engineering.knowledge.connector import KnowledgeItem


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度（零向量安全）。"""

    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class RetrievalResult:
    """单次检索结果（按得分降序的候选集）。"""

    query: str
    candidates: list[tuple[KnowledgeItem, float]] = field(default_factory=list)

    def items(self) -> list[KnowledgeItem]:
        return [item for item, _ in self.candidates]

    def top_k(self, k: int) -> list[KnowledgeItem]:
        return [item for item, _ in self.candidates[:k]]

    def __len__(self) -> int:
        return len(self.candidates)


class KnowledgeRetriever:
    """从 KnowledgeItem 语料检索候选（默认词面，可选 embedding 余弦）。"""

    def __init__(
        self,
        *,
        embedder: Optional[Callable[[str], list[float]]] = None,
        top_k: int = 5,
    ) -> None:
        self._embedder = embedder
        self._top_k = top_k

    def retrieve(
        self,
        query: str,
        corpus: Sequence[KnowledgeItem],
        *,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """检索并返回降序候选集（截断到 top_k）。"""

        k = top_k if top_k is not None else self._top_k
        corpus_list = list(corpus)
        if self._embedder is not None:
            scored = self._cosine_retrieve(query, corpus_list)
        else:
            scored = self._lexical_retrieve(query, corpus_list)
        scored.sort(key=lambda x: x[1], reverse=True)
        return RetrievalResult(query=query, candidates=scored[:k])

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t for t in text.lower().split() if t}

    def _lexical_retrieve(
        self, query: str, corpus: list[KnowledgeItem]
    ) -> list[tuple[KnowledgeItem, float]]:
        q_tokens = self._tokens(query)
        scored: list[tuple[KnowledgeItem, float]] = []
        for item in corpus:
            text = (
                f"{item.title} {item.content} "
                f"{' '.join(item.linked_entities)} {item.domain}"
            )
            doc_tokens = self._tokens(text)
            if not q_tokens or not doc_tokens:
                score = 0.0
            else:
                union = q_tokens | doc_tokens
                score = len(q_tokens & doc_tokens) / len(union)  # Jaccard
            # 领域精确匹配加权（工程域强相关）。
            if item.domain and item.domain.lower() in query.lower():
                score += 0.5
            scored.append((item, score))
        return scored

    def _cosine_retrieve(
        self, query: str, corpus: list[KnowledgeItem]
    ) -> list[tuple[KnowledgeItem, float]]:
        q_vec = self._embedder(query)  # type: ignore[call-arg]
        scored: list[tuple[KnowledgeItem, float]] = []
        for item in corpus:
            text = f"{item.title} {item.content}"
            d_vec = self._embedder(text)  # type: ignore[call-arg]
            scored.append((item, _cosine(q_vec, d_vec)))
        return scored


__all__ = ["KnowledgeRetriever", "RetrievalResult", "_cosine"]
