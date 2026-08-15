"""Phase 3.9.10 —— Security / RBAC / Cross-org Validation（Task 34, 40）。

验证：

- 未授权写被拒
- AI/SYSTEM 危险写被拒
- 跨组织被拒
- Production scope 被拒
- CSRF 强制（标记）
- Identity contract 完整
- Secret 不泄漏

全部 fail-closed。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    CredentialLeakError,
    assert_no_credential_leak,
)


class Actor(str, Enum):
    """请求主体类别。"""

    UNAUTHORIZED = "unauthorized"
    AI_SYSTEM = "ai_system"
    CROSS_ORG = "cross_org"
    SAME_ORG_USER = "same_org_user"
    PRIVILEGED_ROLE = "privileged_role"


class RequestScope(str, Enum):
    """请求作用域。"""

    EXTERNAL_STAGING = "external_staging"
    PRODUCTION = "production"


@dataclass
class SecurityCheckResult:
    """单安全检查结果。"""

    name: str
    allowed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "allowed": self.allowed, "detail": self.detail}


class ExternalStagingSecurityValidator:
    """安全 / RBAC / 跨组织校验（fail-closed 决策器）。"""

    def evaluate_write(
        self,
        *,
        actor: Actor,
        scope: RequestScope,
        same_org: bool,
        csrf_valid: bool,
        privileged_role: bool,
    ) -> SecurityCheckResult:
        # Production scope 一律拒绝
        if scope is RequestScope.PRODUCTION:
            return SecurityCheckResult(
                "production_scope_rejected", False, "Production scope 写入被拒绝（红线）。"
            )
        # 未授权
        if actor is Actor.UNAUTHORIZED:
            return SecurityCheckResult(
                "unauthorized_rejected", False, "未授权主体写入被拒绝。"
            )
        # AI/SYSTEM 危险写
        if actor is Actor.AI_SYSTEM:
            return SecurityCheckResult(
                "ai_system_write_rejected", False, "AI/SYSTEM 危险写被拒绝（需人工主体）。"
            )
        # 跨组织
        if actor is Actor.CROSS_ORG or not same_org:
            return SecurityCheckResult(
                "cross_org_rejected", False, "跨组织请求被拒绝。"
            )
        # CSRF
        if not csrf_valid:
            return SecurityCheckResult(
                "csrf_enforced", False, "CSRF 校验失败，写入被拒绝。"
            )
        # 需要特权角色但无
        if not privileged_role:
            return SecurityCheckResult(
                "privileged_role_required", False, "缺少特权角色，写入被拒绝。"
            )
        return SecurityCheckResult(
            "write_allowed_same_org_privileged", True, "同组织特权角色，写入允许（仅 External Staging）。"
        )

    def assert_no_secret_leak(self, *, text: str = "", mapping: dict | None = None) -> None:
        """凭据不泄漏校验。"""

        try:
            assert_no_credential_leak(text=text or None, mapping=mapping or None)
        except CredentialLeakError as exc:
            raise CredentialLeakError(f"安全校验拦截凭据泄漏：{exc}")

    def identity_contract_intact(self, environment: dict[str, Any]) -> SecurityCheckResult:
        """Identity contract 完整性（production=false 等）。"""

        ok = environment.get("production") is False and environment.get("environment") in (
            "external_staging",
            "local_staging",
        )
        return SecurityCheckResult(
            "identity_contract_intact",
            ok,
            "环境身份 contract 完整（production=false, 非 production 域）。" if ok else "环境身份 contract 违例。",
        )


__all__ = [
    "Actor",
    "RequestScope",
    "SecurityCheckResult",
    "ExternalStagingSecurityValidator",
]
