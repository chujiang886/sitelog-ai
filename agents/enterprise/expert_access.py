"""Enterprise Operation Layer —— 专家权限隔离（任务3，Phase 3.8.1）。

``ExpertAccessPolicy``：限制专家只能审核其**授权范围内**的内容（按 project / solution /
专业领域 domain 维度），范围外默认拒绝（fail-closed）。

设计：
- 专家授权范围由 ``authorized_project_ids`` / ``authorized_solution_ids`` / ``authorized_domains``
  三维声明。
- ``can_review`` 默认拒绝（任何未显式授权的目标都返回 False）。
- 跨域访问抛 ``EnterpriseIsolationError``（企业级隔离）。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 不持有任何批准/审批/报价方法（红线②/③/④）。
- 专家审阅结论只是专业意见（``PROVIDE_EXPERTISE``），须经真实人工审核/批准（红线⑥ 由审计层保障）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from agents.enterprise.audit import AuditService
from agents.enterprise.identity import User
from agents.enterprise.organization import EnterpriseIsolationError, OrganizationService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


@dataclass
class ExpertAccessPolicy:
    """专家的授权审核范围（fail-closed：范围外默认拒绝）。"""

    expert_user_id: str
    org_id: str
    authorized_project_ids: frozenset[str] = field(default_factory=frozenset)
    authorized_solution_ids: frozenset[str] = field(default_factory=frozenset)
    authorized_domains: frozenset[str] = field(default_factory=frozenset)


class ExpertAccessService:
    """专家权限隔离服务（任务3）。"""

    def __init__(self, org_id: str, audit: Optional[AuditService] = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 ExpertAccessService"
                "（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._policies: dict[str, ExpertAccessPolicy] = {}

    def define_policy(
        self,
        *,
        expert_user_id: str,
        authorized_project_ids: Iterable[str] = (),
        authorized_solution_ids: Iterable[str] = (),
        authorized_domains: Iterable[str] = (),
    ) -> ExpertAccessPolicy:
        """登记/更新专家的授权审核范围（写路径，断言红线①/⑤）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下定义专家策略（红线①/⑤）"
            )
        policy = ExpertAccessPolicy(
            expert_user_id=expert_user_id,
            org_id=self._org_id,
            authorized_project_ids=frozenset(authorized_project_ids),
            authorized_solution_ids=frozenset(authorized_solution_ids),
            authorized_domains=frozenset(authorized_domains),
        )
        self._policies[expert_user_id] = policy
        if self._audit is not None:
            self._audit.record_access_granted(
                record_id=f"expert-policy-{expert_user_id}",
                actor_id=expert_user_id,
                action="define_expert_access_policy",
                target=expert_user_id,
                detail=f"projects={sorted(policy.authorized_project_ids)};"
                f"solutions={sorted(policy.authorized_solution_ids)};"
                f"domains={sorted(policy.authorized_domains)}",
            )
        return policy

    def can_review(
        self,
        *,
        expert: User,
        project_id: str = "",
        solution_id: str = "",
        domain: str = "",
    ) -> bool:
        """专家是否能审核该目标（默认拒绝；范围外一律 False）。

        跨域专家（``expert.org_id != self._org_id``）抛隔离错误。
        """
        OrganizationService.assert_same_org(
            self._org_id, expert.org_id, context=f"专家 {expert.user_id!r} 审核越域"
        )
        policy = self._policies.get(expert.user_id)
        allowed = False
        if policy is not None:
            if project_id and project_id in policy.authorized_project_ids:
                allowed = True
            if solution_id and solution_id in policy.authorized_solution_ids:
                allowed = True
            if domain and domain in policy.authorized_domains:
                allowed = True
        if self._audit is not None:
            self._audit.record_permission_check(
                record_id=f"expert-check-{expert.user_id}",
                actor_id=expert.user_id,
                action="expert_review_permission_check",
                target=project_id or solution_id or domain,
                detail=f"project={project_id};solution={solution_id};domain={domain};"
                f"allowed={allowed}",
            )
            if allowed:
                self._audit.record_access_granted(
                    record_id=f"expert-granted-{expert.user_id}",
                    actor_id=expert.user_id,
                    action="expert_review_access_granted",
                    target=project_id or solution_id or domain,
                )
            else:
                self._audit.record_access_denied(
                    record_id=f"expert-denied-{expert.user_id}",
                    actor_id=expert.user_id,
                    action="expert_review_access_denied",
                    target=project_id or solution_id or domain,
                )
        return allowed


__all__ = [
    "ExpertAccessPolicy",
    "ExpertAccessService",
]
