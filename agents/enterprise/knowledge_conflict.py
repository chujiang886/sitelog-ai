"""Enterprise Knowledge Governance & Version Control Layer —— 知识版本冲突（任务4，Phase 3.8.8）。

新增：
- ``KnowledgeConflictCandidate``：知识版本冲突候选（conflict_id / knowledge_a / knowledge_b
  / reason / evidence / requires_human_review）。
- ``KnowledgeConflictService``：仅**发现**知识冲突；**禁止** AI 自动 merge（red line ③）。

红线（fail-closed，复用 3.8.0~3.8.7 基座 + 3.8.8 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **只发现冲突，禁止自动 merge**（``requires_human_review`` 恒 True，红线③/⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动合并入口（``auto_update_knowledge`` / ``auto_merge_knowledge`` /
  ``auto_approve_knowledge``，红线③/⑤）。
- 本服务**不**承载任何经营决策/审批/管理建议入口（红线④/⑤）。
- 可选联动 ``AuditService.record_knowledge_conflict_action`` 如实标注发起方 actor
  （AI 发现默认 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


@dataclass
class KnowledgeConflictCandidate:
    """知识版本冲突候选（任务4）。

    只描述「发现 knowledge_a 与 knowledge_b 之间的冲突 + 原因 + 证据」，不自动合并、不审批、
    不代管理责任；``requires_human_review`` 恒为 True（冲突解决须人工，红线③/⑥）。
    """

    conflict_id: str
    knowledge_a: str                   # 冲突方 A（knowledge_id 或 version_id）
    knowledge_b: str                   # 冲突方 B（knowledge_id 或 version_id）
    reason: str                        # 冲突原因描述
    evidence: str                      # 支撑证据（关联版本哈希/来源溯源）
    org_id: str = ""                   # 归属组织（隔离作用域）
    requires_human_review: bool = True  # 恒为 True：冲突解决须经人工（红线③/⑥）
    created_at: str = ""

    def __post_init__(self) -> None:
        # 红线③/⑥：任何冲突发现都强制要求人工介入解决，AI 不代管理做判断。
        self.requires_human_review = True


class KnowledgeConflictService(_RedLineForbiddenMixin):
    """知识冲突服务（任务4）。

    仅发现/读取知识冲突候选；跨域访问抛 ``EnterpriseIsolationError``；写路径断言
    ``safety_invariants_ok()``（红线①/⑤）。本服务**只发现冲突**，**绝不**自动合并
    （red line ③）：不持有 apply / merge / commit / write / auto_merge_knowledge。
    本服务**不**持有 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_update_knowledge / auto_approve_knowledge
    等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动改/合并/批准知识（核心：只发现冲突，绝不 merge）
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "apply",
        "merge",
        "commit",
        "write",
        # 红线④/⑤：禁止自动经营决策 / 审批 / 管理建议
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "recommend",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "AnalyticsVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeConflictService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._conflicts: dict[str, KnowledgeConflictCandidate] = {}

    def discover_conflict(
        self,
        *,
        conflict_id: str,
        knowledge_a: str,
        knowledge_b: str,
        reason: str,
        evidence: str,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeConflictCandidate:
        """发现一条知识冲突候选（默认 AI 发现，requires_human_review 恒 True，待人工解决）。

        本方法**只**登记冲突事实，**绝不**自动合并冲突双方（red line ③）。登记后如实记录
        ``record_knowledge_conflict_action``（actor 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下发现知识冲突（红线①/⑤）"
            )
        conf = KnowledgeConflictCandidate(
            conflict_id=conflict_id,
            knowledge_a=knowledge_a,
            knowledge_b=knowledge_b,
            reason=reason,
            evidence=evidence,
            org_id=self._org_id,
            created_at=created_at,
        )
        self._conflicts[conflict_id] = conf
        if self._audit is not None:
            self._audit.record_knowledge_conflict_action(
                record_id=f"conflict-{conflict_id}",
                actor_id=actor_id,
                action="discover_knowledge_conflict",
                target=conflict_id,
                detail=(
                    f"knowledge_a={knowledge_a};knowledge_b={knowledge_b};"
                    f"reason={reason};evidence={evidence}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return conf

    def get(self, *, conflict_id: str) -> KnowledgeConflictCandidate:
        """按组织作用域读取冲突（跨域访问抛隔离错误）。"""
        return self._get_scoped(conflict_id)

    def list_conflicts(
        self,
        *,
        knowledge_id: str = "",
        requires_human_review: "bool | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[KnowledgeConflictCandidate]:
        """列出当前组织下冲突（可按涉及 knowledge_id / 是否需人工解决过滤）。"""
        out = [c for c in self._conflicts.values() if c.org_id == self._org_id]
        if knowledge_id:
            out = [
                c
                for c in out
                if c.knowledge_a == knowledge_id or c.knowledge_b == knowledge_id
            ]
        if requires_human_review is not None:
            out = [c for c in out if c.requires_human_review == requires_human_review]
        return out

    def _get_scoped(self, conflict_id: str) -> KnowledgeConflictCandidate:
        from agents.enterprise.organization import EnterpriseIsolationError

        conf = self._conflicts.get(conflict_id)
        if conf is None:
            raise EnterpriseIsolationError(f"知识冲突 {conflict_id!r} 不存在")
        if conf.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识冲突 {conflict_id!r} 归属组织 {conf.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return conf


__all__ = [
    "KnowledgeConflictCandidate",
    "KnowledgeConflictService",
]
