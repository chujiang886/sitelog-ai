"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 知识上下文（任务3，Phase 3.8.9）。

新增：``KnowledgeTrace``（单条溯源记录）+ ``KnowledgeContext``（可追溯的检索上下文聚合）。

设计要点：
- ``KnowledgeContext`` 聚合一组候选知识项（``KnowledgeItem``），并自动派生 ``sources`` /
  ``versions`` / ``trace``，**确保所有知识可溯源**（任务3 核心要求）。
- 纯数据聚合容器，不写任何知识资产、不生成工程结论（red line ③/④）。
- 不持有任何批准/报价/审批/记录为人工方法（红线②/③/④/⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.enterprise.knowledge_retrieval import KnowledgeItem


@dataclass
class KnowledgeTrace:
    """单条知识溯源记录（任务3）。

    把某知识项的 id / 来源 / 版本 / 归属组织绑定在一起，使上下文中的每条知识都可回溯。
    """

    knowledge_id: str
    source: str
    version: str                   # 关联版本号（空表示无版本）
    org_id: str = ""


@dataclass
class KnowledgeContext:
    """可追溯的检索上下文（任务3）。

    由 ``KnowledgeRetrievalEngine.retrieve_context`` 拼装；``__post_init__`` 自动从候选项派生
    ``sources``（去重来源集合）、``versions``（去重版本集合）、``trace``（逐条溯源）。
    所有知识须可追溯：缺来源的项仍会被记入 trace（source 为空），便于审计发现缺口。
    """

    context_id: str
    knowledge_items: list[KnowledgeItem]
    org_id: str = ""
    sources: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    trace: list[KnowledgeTrace] = field(default_factory=list)

    def __post_init__(self) -> None:
        sources: list[str] = []
        versions: list[str] = []
        trace: list[KnowledgeTrace] = []
        for it in self.knowledge_items:
            if it.source and it.source not in sources:
                sources.append(it.source)
            v = it.version or ""
            if v and v not in versions:
                versions.append(v)
            trace.append(
                KnowledgeTrace(
                    knowledge_id=it.knowledge_id,
                    source=it.source,
                    version=v,
                    org_id=it.org_id,
                )
            )
        # 仅当未显式预填时才覆盖，避免重复构造时丢失调用方意图。
        if not self.sources:
            self.sources = sources
        if not self.versions:
            self.versions = versions
        if not self.trace:
            self.trace = trace

    def has_source_gaps(self) -> bool:
        """是否存在缺来源的知识项（用于审计/人工复核提示）。"""
        return any(not t.source for t in self.trace)

    def item_ids(self) -> list[str]:
        """返回上下文中所有知识项 id。"""
        return [it.knowledge_id for it in self.knowledge_items]


__all__ = ["KnowledgeTrace", "KnowledgeContext"]
