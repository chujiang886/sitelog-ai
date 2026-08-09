"""Enterprise Operation Layer —— 审核权限隔离 / 职责分离（SoD）（任务4，Phase 3.8.1）。

``ReviewPermission``：确保**审核者 / 提交者 / 专家**三角色分离（Separation of Duties）。

规则（fail-closed）：
- 提交者**不得**审核自己提交的内容（self-review 禁止）。
- 审核者必须是 ``REVIEWER`` 角色（管理员可代行，但同样受 self-review 限制）。
- 专家仅提供专业意见，**不得**对同一条目既提交又审核，亦不得兼任审核者。
- 跨域访问抛 ``EnterpriseIsolationError``（企业级隔离）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有任何批准/审批/报价方法（红线②/③/④）；审核结论须经真实人工批准（红线⑥ 由审计层保障）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import RoleKind, User
from agents.enterprise.organization import EnterpriseIsolationError, OrganizationService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


class ReviewDecision(str, Enum):
    """审核权限校验结果。"""

    ALLOWED = "allowed"
    DENIED_SUBMITTER_IS_REVIEWER = "denied_submitter_is_reviewer"
    DENIED_REVIEWER_NOT_AUTHORIZED = "denied_reviewer_not_authorized"
    DENIED_EXPERT_CONFLICT = "denied_expert_conflict"


@dataclass
class ReviewContext:
    """一次审核的三角色上下文。"""

    review_id: str
    org_id: str
    submitter_id: str
    reviewer_id: str
    expert_id: str = ""
    target_id: str = ""


class ReviewPermissionService:
    """审核权限隔离 / 职责分离服务（任务4）。"""

    def __init__(self, org_id: str, audit: Optional[AuditService] = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 ReviewPermissionService"
                "（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit

    def validate(
        self,
        *,
        submitter: User,
        reviewer: User,
        expert: Optional[User] = None,
        target_id: str = "",
        review_id: str = "",
    ) -> bool:
        """校验本次审核是否满足职责分离（SoD）。返回 True 表示允许审核。

        跨域（submitter / reviewer / expert 任一归属非本组织）抛 ``EnterpriseIsolationError``。
        """
        OrganizationService.assert_same_org(
            self._org_id, submitter.org_id, context="提交者越域"
        )
        OrganizationService.assert_same_org(
            self._org_id, reviewer.org_id, context="审核者越域"
        )
        if expert is not None:
            OrganizationService.assert_same_org(
                self._org_id, expert.org_id, context="专家越域"
            )

        decision = ReviewDecision.ALLOWED

        # 规则1：自审禁止（提交者 == 审核者）。
        if submitter.user_id == reviewer.user_id:
            decision = ReviewDecision.DENIED_SUBMITTER_IS_REVIEWER

        # 规则2：审核者必须是 REVIEWER 角色（或管理员）。
        if decision == ReviewDecision.ALLOWED:
            if not (reviewer.is_admin() or reviewer.role.kind == RoleKind.REVIEWER):
                decision = ReviewDecision.DENIED_REVIEWER_NOT_AUTHORIZED

        # 规则3：专家不得兼任提交者或审核者（职责分离）。
        if decision == ReviewDecision.ALLOWED and expert is not None:
            if expert.user_id == reviewer.user_id or expert.user_id == submitter.user_id:
                decision = ReviewDecision.DENIED_EXPERT_CONFLICT

        allowed = decision == ReviewDecision.ALLOWED
        if self._audit is not None:
            self._audit.record_permission_check(
                record_id=f"review-check-{review_id or target_id}",
                actor_id=reviewer.user_id,
                action="review_permission_check",
                target=target_id or review_id,
                detail=f"submitter={submitter.user_id};reviewer={reviewer.user_id};"
                f"expert={expert.user_id if expert else ''};decision={decision.value}",
            )
            if allowed:
                self._audit.record_access_granted(
                    record_id=f"review-granted-{review_id or target_id}",
                    actor_id=reviewer.user_id,
                    action="review_access_granted",
                    target=target_id or review_id,
                )
            else:
                self._audit.record_access_denied(
                    record_id=f"review-denied-{review_id or target_id}",
                    actor_id=reviewer.user_id,
                    action="review_access_denied",
                    target=target_id or review_id,
                    detail=f"decision={decision.value}",
                )
        return allowed


__all__ = [
    "ReviewDecision",
    "ReviewContext",
    "ReviewPermissionService",
]
