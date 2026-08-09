"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 知识更新候选（任务3，Phase 3.8.7）。

新增：
- ``KnowledgeChangeType``：候选变更类型（add / update / delete / correct / clarify）。
- ``KnowledgeUpdateCandidate``：知识更新候选（candidate_id / org_id / source /
  change_type / content / evidence / requires_human_review）。
- ``KnowledgeUpdateCandidateService``：仅**提议**知识更新候选；**禁止**自动写入任何
  知识库（red line ③：代码库无 KnowledgeRepository，本服务也绝不持有 apply/merge/
  approve 等方法）。候选必须经人工复核（requires_human_review 恒为 True）。

红线（fail-closed，复用 3.8.0~3.8.6 基座 + 3.8.7 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``requires_human_review`` 恒为 True（AI 不代管理判断，红线③/⑥）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截自动改知识入口（``auto_update_knowledge`` / ``auto_merge_knowledge`` /
  ``auto_approve_knowledge``）与自动经营决策入口（红线④/⑤）。
- **不提供** apply / merge / approve / write / commit 等将候选落地为知识资产的方法
  （落地须由真实人工在知识库侧执行，AI 只提候选）。
- 可选联动 ``AuditService.record_knowledge_candidate_action`` 如实标注发起方 actor
  （AI 提议默认 AI，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


class KnowledgeChangeType(str, Enum):
    """知识更新候选变更类型（任务3）。

    仅描述「拟对知识做何种修改」，不承载任何决策/批准语义；实际落地须经人工复核。
    """

    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    CORRECT = "correct"
    CLARIFY = "clarify"


@dataclass
class KnowledgeUpdateCandidate:
    """知识更新候选（任务3）。

    只描述「建议如何改知识 + 证据来源」，不落地、不审批、不代管理责任；
    ``requires_human_review`` 恒为 True（AI 不代管理做判断，红线③/⑥）。
    """

    candidate_id: str
    org_id: str
    source: str                       # 候选来源（如 feedback-xxx / validation-yyy / manual ...）
    change_type: KnowledgeChangeType
    content: str                      # 候选内容（拟新增/修改的知识事实）
    evidence: str                     # 支撑证据（关联 feedback / validation / 报告等溯源）
    requires_human_review: bool = True  # 恒为 True：必须经人工复核（红线③/⑥）
    created_at: str = ""

    def __post_init__(self) -> None:
        # 红线③/⑥：任何知识更新候选都强制要求人工复核，AI 不代管理做判断。
        self.requires_human_review = True


class KnowledgeUpdateCandidateService(_RedLineForbiddenMixin):
    """知识更新候选服务（任务3）。

    仅提议/读取知识更新候选；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。本服务**只提候选**，**绝不**自动
    写入任何知识库（red line ③）：不持有 apply / merge / approve / write / commit 等方法。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_update_knowledge 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③：禁止 AI 自动改知识（核心：只提候选，绝不落地）
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
                "KnowledgeUpdateCandidateService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._candidates: dict[str, KnowledgeUpdateCandidate] = {}

    def propose_candidate(
        self,
        *,
        candidate_id: str,
        source: str,
        change_type: KnowledgeChangeType,
        content: str,
        evidence: str,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeUpdateCandidate:
        """提议一条知识更新候选（默认 AI 提议，requires_human_review 恒 True，待人工复核）。

        本方法**只**登记候选，**绝不**写入任何知识库（red line ③）。
        登记后如实记录 ``record_knowledge_candidate_action``（actor 默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提议知识候选（红线①/⑤）"
            )
        cand = KnowledgeUpdateCandidate(
            candidate_id=candidate_id,
            org_id=self._org_id,
            source=source,
            change_type=change_type,
            content=content,
            evidence=evidence,
            created_at=created_at,
        )
        self._candidates[candidate_id] = cand
        if self._audit is not None:
            self._audit.record_knowledge_candidate_action(
                record_id=f"candidate-{candidate_id}",
                actor_id=actor_id,
                action="propose_knowledge_candidate",
                target=candidate_id,
                detail=(
                    f"source={source};change_type={change_type.value};"
                    f"evidence={evidence}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return cand

    def get(self, *, candidate_id: str) -> KnowledgeUpdateCandidate:
        """按组织作用域读取候选（跨域访问抛隔离错误）。"""
        return self._get_scoped(candidate_id)

    def list_candidates(
        self,
        *,
        source: str = "",
        requires_human_review: "bool | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[KnowledgeUpdateCandidate]:
        """列出当前组织下候选（可按 source / 是否需人工复核过滤）。"""
        out = [c for c in self._candidates.values() if c.org_id == self._org_id]
        if source:
            out = [c for c in out if c.source == source]
        if requires_human_review is not None:
            out = [c for c in out if c.requires_human_review == requires_human_review]
        return out

    def _get_scoped(self, candidate_id: str) -> KnowledgeUpdateCandidate:
        from agents.enterprise.organization import EnterpriseIsolationError

        cand = self._candidates.get(candidate_id)
        if cand is None:
            raise EnterpriseIsolationError(f"知识更新候选 {candidate_id!r} 不存在")
        if cand.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"知识更新候选 {candidate_id!r} 归属组织 {cand.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return cand


__all__ = [
    "KnowledgeChangeType",
    "KnowledgeUpdateCandidate",
    "KnowledgeUpdateCandidateService",
]
