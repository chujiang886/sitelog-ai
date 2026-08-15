"""Phase 3.9.13 —— 执行安全审计（security_execution，§七 递归深扫 + 双钥匙一致性）。

叠加两条纪律：
1. 递归凭据深扫：对确定性执行包做 fail-closed 扫描（禁止明文凭据落盘）。
2. 双钥匙一致性：机器钥匙有效但真人授权缺失 → 一致性成立（即「未授权」，符合预期）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.credential_deep_scanner import (
    assert_no_deep_credential_leak,
)
from agents.external_staging_provisioning.authorization_registry import (
    ProvisioningAuthorizationRegistry,
)


@dataclass
class ExecutionSecurityResult:
    deep_scan_clean: bool
    dual_key_authorized: bool
    consistent: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "deep_scan_clean": self.deep_scan_clean,
            "dual_key_authorized": self.dual_key_authorized,
            "consistent": self.consistent,
            "detail": self.detail,
        }


class ExecutionSecurityAuditor:
    """执行安全审计器（fail-closed）。"""

    def audit(
        self, *, package: dict[str, Any], auth: ProvisioningAuthorizationRegistry
    ) -> dict[str, Any]:
        assert_no_deep_credential_leak(json_str=json.dumps(package, ensure_ascii=False))
        dual = auth.is_authorized_for_apply()
        consistent = auth.machine_key_present() and (not auth.human_key_present())
        return ExecutionSecurityResult(
            deep_scan_clean=True,
            dual_key_authorized=dual,
            consistent=consistent,
            detail=(
                "递归深扫无明文凭据；机器钥匙有效、真人授权缺失（预期待授权态）。"
                if consistent
                else "双钥匙一致性异常，需人工复核。"
            ),
        ).to_dict()


__all__ = ["ExecutionSecurityAuditor", "ExecutionSecurityResult"]
