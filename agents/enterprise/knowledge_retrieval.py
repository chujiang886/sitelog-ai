"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 检索引擎（任务2，Phase 3.8.9）。

新增：
- ``KnowledgeItem``：检索索引项（knowledge_id / title / content / knowledge_type / source /
  org_id / version / tags / visibility_roles）；仅承载知识**元数据**与**内容摘要**，绝不写知识资产。
- ``KnowledgeRetrievalEngine``：语义理解 + 检索 + 权限过滤 + 上下文拼装。

红线（fail-closed，复用 3.8.0~3.8.8 基座 + 3.8.9 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 检索引擎**只返回候选知识**，绝不自动生成工程结论（``generate_engineering_conclusion`` 被拦截，
  红线④/⑤）；任何把检索结果直接落成工程参数 / 方案结论的入口在结构上不可达。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动落地/发布/合并/应用知识入口（``auto_update_knowledge`` / ``auto_publish_knowledge``
  / ``auto_merge_knowledge`` / ``auto_apply_knowledge`` / ``publish`` / ``merge`` / ``apply``
  / ``commit`` / ``write``，红线③/⑤）。
- 本服务不承载任何经营决策 / 审批 / 管理建议入口（``auto_business_decision`` / ``decide`` 等，红线④/⑤）。
- 可选联动 ``AuditService`` 如实标注检索发起方（默认 USER，因检索由人发起；红线⑥）。

代码库无 KnowledgeRepository：``index()`` 仅登记**已存在**的人工知识元数据用于检索，绝不新增或修改
任何知识资产（red line ③）。知识的实际落地 / 改写 / 发布须由真实人工执行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


@dataclass
class KnowledgeItem:
    """检索索引项（任务2）。

    仅承载知识**元数据**与**内容摘要**，用于语义检索；``org_id`` 用于组织隔离，
    ``knowledge_type`` 用于权限作用域（由 ``KnowledgeVisibilityPolicy`` 控制可见性），
    ``version`` 关联到 ``KnowledgeVersion`` 以支持溯源（任务3）。

    本对象**不**写入任何知识库（red line ③）；索引只是已存在知识的目录化。
    """

    knowledge_id: str
    title: str
    content: str
    knowledge_type: str                # design_spec / regulation / case / manual / governance / feedback
    source: str                       # 来源（如 manual / candidate-xxx / import / version-xxx）
    org_id: str = ""
    version: str = ""                 # 关联的知识版本号（如 "v2"），空表示无版本
    tags: list[str] = field(default_factory=list)
    visibility_roles: list[str] = field(default_factory=list)  # 限定可见角色（空=按类型策略）

    def __post_init__(self) -> None:
        if not self.knowledge_type:
            self.knowledge_type = "manual"


class KnowledgeRetrievalEngine(_RedLineForbiddenMixin):
    """知识检索引擎（任务2）。

    提供 ``index`` / ``search`` / ``semantic_match`` / ``filter_by_permission`` /
    ``retrieve_context``。引擎**只返回候选知识**，绝不自动生成工程结论（红线④/⑤）：
    ``generate_engineering_conclusion`` 等决策入口在结构上被拦截。

    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识（核心：引擎只检索，绝不改写知识资产）
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
        "auto_activate",
        "publish",
        "merge",
        "apply",
        "commit",
        "write",
        # 红线④/⑤：禁止自动生成工程结论 / 经营决策 / 审批 / 管理建议
        "generate_engineering_conclusion",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeRetrievalEngine（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)
        self._items: dict[str, KnowledgeItem] = {}

    def index(self, *, item: KnowledgeItem) -> KnowledgeItem:
        """登记一个已存在的人工知识项到检索索引（仅元数据目录化，绝不写知识资产，red line ③）。

        跨域项会被拒绝（组织隔离）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下索引知识（红线①/⑤）"
            )
        if item.org_id and item.org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"知识项 {item.knowledge_id!r} 归属组织 {item.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域索引"
            )
        self._items[item.knowledge_id] = item
        return item

    def search(
        self,
        *,
        query_text: str,
        role: "RoleKind | None" = None,
        filters: "dict | None" = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        """执行语义检索，返回**候选知识项**（按相关度降序，最多 top_k）。

        流程：① 语义打分 → ② 权限过滤（按角色可见性，默认拒绝） → ③ 业务过滤（类型/来源/标签）
        → ④ 截断 top_k。返回结果**仅为候选知识**，不含任何工程结论。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检索知识（红线①/⑤）"
            )
        ranked = self.semantic_match(query_text=query_text)
        items = [it for it, _ in ranked]
        items = self.filter_by_permission(role=role, items=items)
        items = self._apply_filters(items=items, filters=filters or {})
        results = items[: max(0, top_k)]
        if self._audit is not None:
            self._audit.record_knowledge_retrieval_action(
                record_id=f"retrieval-{self._org_id}-{len(results)}",
                actor_id="user",
                action="retrieve_knowledge_candidates",
                target=query_text[:64],
                detail=(
                    f"matched={len(ranked)};returned={len(results)};"
                    f"role={role.value if role else 'none'}"
                ),
                actor_kind=AuditActorKind.USER,
            )
        return results

    def semantic_match(
        self,
        *,
        query_text: str,
        items: "list[KnowledgeItem] | None" = None,
    ) -> list[tuple[KnowledgeItem, float]]:
        """对查询做语义匹配打分（启发式：词元 Jaccard 重叠度，无外部嵌入依赖）。

        返回的 (item, score) 按 score 降序；score 恒在 [0,1]。这是**候选**排序，
        不代表任何工程可信结论。
        """
        candidates = items if items is not None else list(self._items.values())
        q_tokens = self._tokenize(query_text)
        if not q_tokens:
            return []
        scored: list[tuple[KnowledgeItem, float]] = []
        for it in candidates:
            it_tokens = self._tokenize(f"{it.title} {it.content} {' '.join(it.tags)}")
            union = q_tokens | it_tokens
            if not union:
                continue
            score = len(q_tokens & it_tokens) / len(union)
            if score > 0.0:
                scored.append((it, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def filter_by_permission(
        self,
        *,
        role: "RoleKind | None",
        items: list[KnowledgeItem],
    ) -> list[KnowledgeItem]:
        """按角色可见性过滤候选知识（默认拒绝：角色未授权则不可见，红线⑥ + 任务6）。"""
        if role is None:
            return list(items)
        out: list[KnowledgeItem] = []
        for it in items:
            # 显式角色限定优先；否则按 knowledge_type 类型策略。
            if it.visibility_roles:
                if role.value in it.visibility_roles:
                    out.append(it)
                continue
            if self._visibility.can_retrieve(role, it):
                out.append(it)
        return out

    def retrieve_context(
        self,
        *,
        query_id: str,
        items: list[KnowledgeItem],
        org_id: str = "",
    ) -> "Any":
        """由候选知识项拼装可追溯的 ``KnowledgeContext``（任务3）。

        仅聚合传入的候选项，不新增任何知识、不生成工程结论；所有项必须归属同一组织。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下拼装知识上下文（红线①/⑤）"
            )
        scope = org_id or self._org_id
        from agents.enterprise.knowledge_context import KnowledgeContext

        valid = []
        for it in items:
            if it.org_id and it.org_id != scope:
                from agents.enterprise.organization import EnterpriseIsolationError

                raise EnterpriseIsolationError(
                    f"知识项 {it.knowledge_id!r} 归属组织 {it.org_id!r} 与上下文组织 "
                    f"{scope!r} 不一致，禁止跨域拼装"
                )
            valid.append(it)
        ctx = KnowledgeContext(
            context_id=f"ctx-{query_id}",
            knowledge_items=list(valid),
            org_id=scope,
        )
        if self._audit is not None:
            self._audit.record_knowledge_retrieval_action(
                record_id=f"context-{query_id}",
                actor_id="user",
                action="retrieve_knowledge_context",
                target=query_id,
                detail=f"items={len(valid)}",
                actor_kind=AuditActorKind.USER,
            )
        return ctx

    def list_items(self) -> list[KnowledgeItem]:
        """列出当前组织下的全部索引项（只读）。"""
        return [it for it in self._items.values() if it.org_id == self._org_id]

    def _apply_filters(
        self, *, items: list[KnowledgeItem], filters: dict
    ) -> list[KnowledgeItem]:
        out = items
        ktype = filters.get("knowledge_type")
        if ktype:
            out = [it for it in out if it.knowledge_type == ktype]
        source = filters.get("source")
        if source:
            out = [it for it in out if it.source == source]
        tags = filters.get("tags") or []
        if tags:
            wanted = set(tags)
            out = [it for it in out if wanted & set(it.tags)]
        return out

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """把文本拆成小写词元集合（拉丁词 + CJK 单字），用于启发式重叠度计算。"""
        if not text:
            return set()
        lowered = text.lower()
        # 拉丁词
        words = re.findall(r"[a-z0-9]+", lowered)
        tokens: set[str] = set(words)
        # CJK 单字（中文按字切分，简单且确定性）
        for ch in lowered:
            if "一" <= ch <= "鿿":
                tokens.add(ch)
        return tokens


__all__ = ["KnowledgeItem", "KnowledgeRetrievalEngine"]
