"""Enterprise Knowledge Agent Orchestration Layer —— 校验智能体（任务3，Phase 3.8.10）。

新增：``KnowledgeValidationAgent``（AI 智能体）+ ``KnowledgeAgentValidationResult``。

职责（红线严格限定）：
- 对检索智能体产出的 ``KnowledgeContext`` 做**来源 / 版本 / 权限 / 溯源**四维校验，
  输出 ``KnowledgeAgentValidationResult``（passed / issues / requires_human_review）。
- **绝不自动批准回答**：校验智能体只产出「知识上下文质量校验结果」，是否采信交由真实人工
  复核（``requires_human_review`` 强制 True，红线⑥：禁止 AI 代责审批）。
- 不持有 approve / auto_approve / engineering_approved 等批准入口（红线②/④/⑥）。
- 可选联动 ``AuditService`` 如实标注发起方（AI 智能体默认 AI，红线⑥：绝不伪造为人工审批）。
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
from agents.enterprise.knowledge_context import KnowledgeContext
from agents.enterprise.knowledge_query_agent import KnowledgeQuery
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


@dataclass
class KnowledgeAgentValidationResult:
    """知识上下文校验结果（任务3）。

    ``passed`` 仅表示「知识上下文在来源/版本/权限/溯源维度上未出现阻断性缺口」，
    **不代表回答已被批准采用**。``requires_human_review`` 强制为 True：是否采信校验结果、
    是否采用后续回答草稿，必须由真实人工决定（红线⑥：AI 不得代责审批）。
    """

    validation_id: str
    query_id: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    requires_human_review: bool = True
    org_id: str = ""

    def __post_init__(self) -> None:
        # 红线⑥：校验结果永远需要真实人工复核，AI 不得替代人工责任。
        self.requires_human_review = True


class KnowledgeValidationAgent(_RedLineForbiddenMixin):
    """校验智能体（任务3）。

    对 ``KnowledgeContext`` 做四维校验（来源可追溯 / 版本完整 / 权限可见 / 溯源非空），
    **绝不自动批准回答**。跨域访问由上下文统一拦截；构造/写路径断言 ``safety_invariants_ok()``
    （红线①/⑤）。

    本智能体**不**持有 approve / auto_approve / engineering_approved /
    auto_apply_knowledge / generate_engineering_conclusion 等方法（红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "auto_approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/⑤：禁止 AI 自动落地/发布/合并/应用知识
        "auto_apply_knowledge",
        "auto_execute_knowledge",
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
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
                "KnowledgeValidationAgent（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)

    def validate(
        self,
        *,
        validation_id: str,
        query: KnowledgeQuery,
        context: KnowledgeContext,
        role: "RoleKind | None" = None,
        actor_id: str = "ai",
    ) -> KnowledgeAgentValidationResult:
        """对检索上下文做四维校验（来源 / 版本 / 权限 / 溯源）。

        **绝不自动批准回答**：``requires_human_review`` 强制 True（红线⑥）。
        如实记录 ``KNOWLEDGE_AGENT_VALIDATE`` 审计（AI 智能体默认 AI，红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行智能体校验（红线①/⑤）"
            )
        issues: list[str] = []

        # ① 溯源非空：上下文必须至少含一条知识溯源。
        if not context.trace:
            issues.append("context_has_no_trace: 检索上下文无溯源记录")

        # ② 来源可追溯：不应存在缺来源的知识项。
        if context.has_source_gaps():
            issues.append("source_gap: 存在缺来源的知识项，来源不可追溯")

        # ③ 版本完整（提醒级，非阻断）：无版本知识项提示人工确认时效。
        missing_version = [t.knowledge_id for t in context.trace if not t.version]
        if missing_version:
            issues.append(
                f"version_missing: {len(missing_version)} 条知识无版本标识，"
                "建议人工确认是否仍为最新"
            )

        # ④ 权限可见：若给定角色，上下文中的知识类型都应对该角色可见（默认拒绝）。
        if role is not None:
            for it in context.knowledge_items:
                if not self._visibility.can_retrieve(role, it):
                    issues.append(
                        f"permission_denied: 知识 {it.knowledge_id!r} 类型 "
                        f"{it.knowledge_type!r} 对角色 {role.value!r} 不可见"
                    )

        passed = not any(
            i.startswith(("context_has_no_trace", "source_gap", "permission_denied"))
            for i in issues
        )
        result = KnowledgeAgentValidationResult(
            validation_id=validation_id,
            query_id=query.query_id,
            passed=passed,
            issues=issues,
            org_id=self._org_id,
        )
        if self._audit is not None:
            self._audit.record_knowledge_agent_validate_action(
                record_id=f"agent-validate-{validation_id}",
                actor_id=actor_id,
                action="agent_validate_knowledge",
                target=validation_id,
                detail=(
                    f"query_id={query.query_id};passed={passed};"
                    f"issues={len(issues)};requires_human_review=true"
                ),
                actor_kind=AuditActorKind.AI,
            )
        return result


__all__ = ["KnowledgeAgentValidationResult", "KnowledgeValidationAgent"]
