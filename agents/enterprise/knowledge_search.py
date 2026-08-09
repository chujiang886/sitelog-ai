"""Enterprise Knowledge Intelligence & Semantic Retrieval Layer —— 知识检索查询（任务1，Phase 3.8.9）。

新增：
- ``KnowledgeSearchQuery``：一次知识检索查询（query_id / org_id / user_id / query_text /
  filters / created_at）；``org_id`` 强制存在以做**组织隔离**（任务1 权限隔离要求）。
- ``KnowledgeSearchService``：组织作用域内的检索查询服务，编排 ``KnowledgeRetrievalEngine``。

红线（fail-closed，复用 3.8.0~3.8.8 基座 + 3.8.9 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 查询/检索**只产出候选知识**，绝不自动生成工程结论（``generate_engineering_conclusion`` 被拦截，
  红线④/⑤）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动落地/发布/合并/应用知识入口（red line ③/⑤）。
- 查询强制 ``org_id``，跨域访问抛 ``EnterpriseIsolationError``（任务1 权限隔离）。
- 可选联动 ``AuditService`` 如实标注查询发起方（默认 USER，因检索由人发起；红线⑥）。
"""

from __future__ import annotations

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
from agents.enterprise.knowledge_retrieval import (
    KnowledgeItem,
    KnowledgeRetrievalEngine,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


@dataclass
class KnowledgeSearchQuery:
    """一次知识检索查询（任务1）。

    ``org_id`` 强制存在：所有查询都在组织作用域内隔离（任务1 权限隔离要求）。``filters`` 为可选
    业务过滤（knowledge_type / source / tags）。
    """

    query_id: str
    org_id: str
    user_id: str
    query_text: str
    filters: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        # 任务1 权限隔离：查询必须归属确定组织，否则拒绝。
        if not self.org_id:
            raise ValueError("KnowledgeSearchQuery 必须携带 org_id 以做组织隔离")
        if self.filters is None:
            self.filters = {}


class KnowledgeSearchService(_RedLineForbiddenMixin):
    """知识检索查询服务（任务1）。

    提供 ``create_query`` / ``run`` / ``run_with_context`` / ``get_query``。编排
    ``KnowledgeRetrievalEngine`` 完成语义检索与上下文拼装。

    跨域访问抛 ``EnterpriseIsolationError``；写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_update_knowledge / auto_apply_knowledge /
    generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识
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
        engine: "KnowledgeRetrievalEngine | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeSearchService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._engine = engine or KnowledgeRetrievalEngine(
            org_id=org_id, audit=audit, identity=identity, visibility=visibility
        )
        self._queries: dict[str, KnowledgeSearchQuery] = {}

    def create_query(
        self,
        *,
        query_id: str,
        user_id: str,
        query_text: str,
        filters: "dict | None" = None,
        created_at: str = "",
        actor_id: str = "user",
        actor_kind: "str | None" = None,
    ) -> KnowledgeSearchQuery:
        """创建一次组织作用域内的检索查询（强制 org_id 隔离，任务1）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建检索查询（红线①/⑤）"
            )
        q = KnowledgeSearchQuery(
            query_id=query_id,
            org_id=self._org_id,
            user_id=user_id,
            query_text=query_text,
            filters=filters or {},
            created_at=created_at,
        )
        self._queries[query_id] = q
        if self._audit is not None:
            self._audit.record_knowledge_search_action(
                record_id=f"search-{query_id}",
                actor_id=actor_id,
                action="create_knowledge_search",
                target=query_id,
                detail=f"user_id={user_id};query={query_text[:64]}",
                ts=created_at,
                actor_kind=actor_kind,
            )
        return q

    def run(
        self,
        *,
        query_id: str,
        role: "RoleKind | None" = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        """执行检索，返回**候选知识项**（只检索，绝不生成工程结论）。"""
        q = self._get_scoped(query_id)
        return self._engine.search(
            query_text=q.query_text, role=role, filters=q.filters, top_k=top_k
        )

    def run_with_context(
        self,
        *,
        query_id: str,
        role: "RoleKind | None" = None,
        top_k: int = 5,
    ) -> "Any":
        """执行检索并拼装可追溯的 ``KnowledgeContext``（任务3）。"""
        items = self.run(query_id=query_id, role=role, top_k=top_k)
        return self._engine.retrieve_context(query_id=query_id, items=items)

    def get_query(self, *, query_id: str) -> KnowledgeSearchQuery:
        """按组织作用域读取查询（跨域访问抛隔离错误）。"""
        return self._get_scoped(query_id)

    def _get_scoped(self, query_id: str) -> KnowledgeSearchQuery:
        from agents.enterprise.organization import EnterpriseIsolationError

        q = self._queries.get(query_id)
        if q is None:
            raise EnterpriseIsolationError(f"检索查询 {query_id!r} 不存在")
        if q.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"检索查询 {query_id!r} 归属组织 {q.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return q


__all__ = ["KnowledgeSearchQuery", "KnowledgeSearchService"]
