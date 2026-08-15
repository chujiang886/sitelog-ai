"""Phase 3.9.11 —— 执行层 API 契约 SSOT（Task 33）。

机器可读的 API 契约：仅 ``read`` / ``human_record`` 动作，**无**任何执行/部署/激活端点。
契约用于 CI 基线校验（路由数稳定、无 forbidden action）。
"""

from __future__ import annotations

from typing import Any

PHASE = "3.9.11"
EXPECTED_TOTAL_ROUTES = 7


def build_api_contract() -> dict[str, Any]:
    """构建执行层 API 契约。"""

    routes = [
        {
            "method": "GET",
            "path": "/api/external-staging-execution/status",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-execution/plan",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-execution/gate",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-execution/evidence",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-execution/package",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "GET",
            "path": "/api/external-staging-execution/resources",
            "scope": "external_staging",
            "action": "read",
            "performs_execution": False,
        },
        {
            "method": "POST",
            "path": "/api/external-staging-execution/human-record",
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
            "execute",
            "deploy",
            "activate",
            "rollback_execute",
            "production_write",
            "secret_write",
        ],
        "total_routes": len(routes),
        "routes": routes,
    }


__all__ = ["PHASE", "EXPECTED_TOTAL_ROUTES", "build_api_contract"]
