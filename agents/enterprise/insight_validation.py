"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 洞察验证（任务2，Phase 3.8.7）。

新增：
- ``ValidationResult``：验证结论（valid / invalid / needs_revision）。
- ``InsightValidation``：洞察验证记录（validation_id / org_id / insight_id / validator /
  result / comment / timestamp）。
- ``InsightValidationService``：登记洞察验证；**禁止 AI 自动验证**（create_validation
  必须由真实 USER 发起，红线⑥）。

红线（fail-closed，复用 3.8.0~3.8.6 基座 + 3.8.7 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``create_validation`` 必须 ``require_human_actor(USER)``（红线⑥：AI 不得自动验证洞察）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval``（红线②/④/⑥）。
- 额外拦截 AI 自动验证入口（``auto_validate`` / ``ai_validate``）与自动改知识入口
  （``auto_update_knowledge`` / ``auto_merge_knowledge`` / ``auto_approve_knowledge``，
  红线③）及自动经营决策入口（红线④/⑤）。
- 可选联动 ``AuditService.record_validation_action`` 如实标注发起方 actor（恒 USER，红线⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.enterprise.audit import AuditService, require_human_actor
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.dashboard_visibility import AnalyticsVisibilityPolicy


class ValidationResult(str, Enum):
    """洞察验证结论（任务2）。

    由专家/主理人人工判定；AI 不产出该结论（create_validation 强制 USER，红线⑥）。
    """

    VALID = "valid"
    INVALID = "invalid"
    NEEDS_REVISION = "needs_revision"


@dataclass
class InsightValidation:
    """洞察验证记录（任务2）。

    仅承载「某专家对某洞察的验证结论」这一事实，不承载任何决策/批准语义；
    ``validator`` 必须是真实人工身份（由服务层 require_human_actor 强制）。
    """

    validation_id: str
    org_id: str
    insight_id: str
    validator: str                  # 验证人（真实 USER id）
    result: ValidationResult
    comment: str = ""
    timestamp: str = ""


class InsightValidationService(_RedLineForbiddenMixin):
    """洞察验证服务（任务2）。

    仅登记/读取洞察验证记录；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。验证必须由真实 USER 发起
    （``create_validation`` 强制 ``require_human_actor(USER)``，红线⑥）。
    本服务**不**持有任何 approve / engineering_approved / quote / pricing / sign /
    authorize / record_human_approval / auto_validate / ai_validate 等方法
    （红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线⑥：禁止 AI 自动验证 / 伪造验证
        "auto_validate",
        "ai_validate",
        # 红线③：禁止 AI 自动改知识
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
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
                "InsightValidationService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._validations: dict[str, InsightValidation] = {}

    def create_validation(
        self,
        *,
        validation_id: str,
        insight_id: str,
        validator: str,
        result: ValidationResult,
        comment: str = "",
        timestamp: str = "",
        actor_id: str = "",
        actor_kind: Any = None,
    ) -> InsightValidation:
        """登记一条洞察验证（红线⑥：必须由真实 USER 发起，AI 不得自动验证）。

        ``actor_kind`` 必须严格为 USER，否则抛 ``EnterpriseRedLineViolationError``。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记验证（红线①/⑤）"
            )
        val = InsightValidation(
            validation_id=validation_id,
            org_id=self._org_id,
            insight_id=insight_id,
            validator=validator,
            result=result,
            comment=comment,
            timestamp=timestamp,
        )
        self._validations[validation_id] = val
        if self._audit is not None:
            self._audit.record_validation_action(
                record_id=f"validation-{validation_id}",
                actor_id=actor_id or validator,
                action="create_validation",
                target=insight_id,
                detail=f"result={result.value};validator={validator}",
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return val

    def get(self, *, validation_id: str) -> InsightValidation:
        """按组织作用域读取验证（跨域访问抛隔离错误）。"""
        return self._get_scoped(validation_id)

    def list_validations(
        self,
        *,
        insight_id: str = "",
        result: "ValidationResult | None" = None,
        role: "RoleKind | None" = None,
    ) -> list[InsightValidation]:
        """列出当前组织下验证（可按 insight_id / result 过滤）。"""
        out = [v for v in self._validations.values() if v.org_id == self._org_id]
        if insight_id:
            out = [v for v in out if v.insight_id == insight_id]
        if result is not None:
            out = [v for v in out if v.result == result]
        return out

    def _get_scoped(self, validation_id: str) -> InsightValidation:
        from agents.enterprise.organization import EnterpriseIsolationError

        val = self._validations.get(validation_id)
        if val is None:
            raise EnterpriseIsolationError(f"洞察验证 {validation_id!r} 不存在")
        if val.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"洞察验证 {validation_id!r} 归属组织 {val.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return val


__all__ = ["ValidationResult", "InsightValidation", "InsightValidationService"]
