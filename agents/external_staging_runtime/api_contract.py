"""Phase 3.9.14 —— External Staging Runtime E2E API 契约（api_contract，仅读端点）。

定义运行时 E2E 资格层的 API 契约：**仅读、禁变更**。任何 mutating 端点
（apply / deploy / migrate / 真实执行）均被列为 forbidden，由后端路由与前端页面共同遵守。
镜像 3.9.13 的 ``EXECUTION_API_CONTRACT`` 结构。
"""

from __future__ import annotations

from typing import Any

EXTERNAL_RUNTIME_API_CONTRACT: dict[str, Any] = {
    "version": "1.0.0",
    "base_path": "/api/v1/external-staging-runtime-e2e",
    "real_execution_allowed": False,
    "real_apply_allowed": False,
    "is_production": False,
    "engineering_enabled": False,
    "endpoints": [
        {
            "path": "/status",
            "method": "GET",
            "mutates": False,
            "description": "整体运行时 E2E 状态（7 层、8 资源全 Pending、apply gate 态）",
        },
        {
            "path": "/isolation",
            "method": "GET",
            "mutates": False,
            "description": "九项隔离审计结论",
        },
        {
            "path": "/qualification",
            "method": "GET",
            "mutates": False,
            "description": "13 项运行时资格结论",
        },
        {
            "path": "/health",
            "method": "GET",
            "mutates": False,
            "description": "Runtime Health 健康形态",
        },
        {
            "path": "/e2e",
            "method": "GET",
            "mutates": False,
            "description": "端到端资格编排计划（6 步，全 plan-only）",
        },
        {
            "path": "/change-control",
            "method": "GET",
            "mutates": False,
            "description": "变更管控 Gate 状态（3.9.14 终端态，永不 GO）",
        },
        {
            "path": "/evidence",
            "method": "GET",
            "mutates": False,
            "description": "无伪造证据链与确定性执行包哈希",
        },
    ],
    "forbidden": [
        "POST /apply",
        "POST /deploy",
        "POST /migrate",
        "POST /execute",
        "PUT /resources/{id}",
        "DELETE /resources/{id}",
        "any endpoint that provisions/registers/connects/isolates/executes a real resource",
    ],
    "note": "AI 不提供任何 mutating 端点；真实 apply/execute 须真人双钥匙在带外执行。",
}


__all__ = ["EXTERNAL_RUNTIME_API_CONTRACT"]
