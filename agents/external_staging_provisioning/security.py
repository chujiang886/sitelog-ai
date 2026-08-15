"""Phase 3.9.12 —— 供给层安全校验（Task 29，复用 credential_scanner）。

fa-closed 安全校验：
- 凭据引用扫描（无明文泄漏）；
- API 契约校验（无 forbidden action：provision/apply/deploy/activate 等）；
- 环境身份 production=false。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_provisioning.api_contract import build_api_contract

# 允许的动作（仅读 + 人工登记）。
ALLOWED_ACTIONS = ("read", "human_record")
# 禁止的动作（任何供给/部署/激活端点都不存在）。
FORBIDDEN_ACTIONS = (
    "provision",
    "apply",
    "deploy",
    "activate",
    "rollback_execute",
    "production_write",
    "secret_write",
)


class ExternalStagingProvisioningSecurityValidator:
    """供给层安全校验器（fail-closed）。"""

    def scan_text(self, text: str) -> list[str]:
        """扫描文本中的明文凭据泄漏（返回命中摘要）。"""

        from agents.external_staging_qualification.credential_scanner import scan_text

        return scan_text(text)

    def assert_no_secret(self, mapping: dict[str, Any]) -> None:
        """断言字典无明文凭据泄漏。"""

        assert_no_credential_leak(mapping=mapping)

    def validate_api_contract(self, contract: dict[str, Any] | None = None) -> bool:
        """校验 API 契约不含 forbidden action，且 allowed_actions 受限。"""

        c = contract or build_api_contract()
        if c.get("no_execution_endpoint") is not True:
            raise ValueError("API 契约必须 no_execution_endpoint=true")
        for r in c.get("routes", []):
            if r.get("action") not in ALLOWED_ACTIONS:
                raise ValueError(f"路由 {r.get('path')} 动作 {r.get('action')} 不在允许集")
            if r.get("performs_execution") is True:
                raise ValueError(f"路由 {r.get('path')} 不得 performs_execution")
        for fa in c.get("forbidden_actions", []):
            if fa not in FORBIDDEN_ACTIONS:
                raise ValueError(f"forbidden_actions 缺 {fa}")
        return True

    def validate_environment_identity(self, identity: dict[str, Any]) -> bool:
        """环境身份 production 必须为 False。"""

        if identity.get("production") is not False:
            raise ValueError("环境身份 production 必须为 False（红线）")
        return True

    def full_check(
        self,
        *,
        bom_mapping: dict[str, Any],
        environment_identity: dict[str, Any],
        contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """组合安全校验，返回结果摘要（fail-closed：任一失败抛错）。"""

        try:
            self.assert_no_secret(bom_mapping)
            secret_ok = True
            secret_detail = "供给 BOM 无明文凭据泄漏。"
        except CredentialLeakError as exc:
            secret_ok = False
            secret_detail = str(exc)

        contract_ok = True
        contract_detail = "API 契约合法（无 forbidden action）。"
        try:
            self.validate_api_contract(contract)
        except ValueError as exc:
            contract_ok = False
            contract_detail = str(exc)

        env_ok = True
        env_detail = "环境身份 production=false。"
        try:
            self.validate_environment_identity(environment_identity)
        except ValueError as exc:
            env_ok = False
            env_detail = str(exc)

        all_ok = secret_ok and contract_ok and env_ok
        return {
            "all_ok": all_ok,
            "credential_reference_safety": secret_ok,
            "credential_detail": secret_detail,
            "api_contract": contract_ok,
            "api_contract_detail": contract_detail,
            "environment_not_production": env_ok,
            "environment_detail": env_detail,
        }


__all__ = [
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    "ExternalStagingProvisioningSecurityValidator",
]
