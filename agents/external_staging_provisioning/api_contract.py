"""Phase 3.9.12 —— 供给算子层 API 契约 SSOT（Task 19）。

机器可读的 API 契约：仅 ``read`` / ``human_record`` 动作，**无**任何供给执行/部署/
激活端点（禁 /provision / /apply / /deploy /activate）。契约用于 CI 基线校验。

复用（治理 复用纪律）：结构同 ``agents.external_staging_execution.api_contract``。
"""

from __future__ import annotations

from typing import Any

PHASE = "3.9.12"
EXPECTED_TOTAL_ROUTES = 7


def build_api_contract() -> dict[str, Any]:
    """构建供给算子层 API 契约。"""

    routes = [
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/status",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/bom",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/gate",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/iac-dry-run",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/package",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-provisioning/runbook",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "POST",
            "path": "/api/external-staging-provisioning/human-input-record",
            "scope": "external_staging",
            "action": "human_record",
            "performs_execution": False,
        },
    ]
    return {
        "schema_version": "1.0.0",
        "phase": PHASE,
        "environment": "external_staging",
        "production": False,
        "production_activation_prohibited": True,
        "engineering_enabled": False,
        "no_execution_endpoint": True,
        "allowed_actions": ["read", "human_record"],
        "forbidden_actions": [
            "provision",
            "apply",
            "deploy",
            "activate",
            "rollback_execute",
            "production_write",
            "secret_write",
        ],
        "operator_gate_states": [
            "blocked",
            "pending_human_input",
            "ready_for_human_provisioning_review",
        ],
        "provisioning_execution_modes": [
            "plan",
            "validate",
            "dry_run",
            "human_authorized_apply",
        ],
        "forbidden_provisioning_modes": ["auto", "production"],
        "total_routes": len(routes),
        "routes": routes,
    }


__all__ = ["PHASE", "EXPECTED_TOTAL_ROUTES", "build_api_contract"]
