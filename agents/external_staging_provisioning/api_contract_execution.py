"""Phase 3.9.13 —— 执行 API 契约（api_contract_execution，仅读端点）。

定义供给执行层的 API 契约：**仅读、禁变更**。任何 mutating 端点（apply / 写资源）
均被列为 forbidden，由后端路由与前端页面共同遵守。
"""

from __future__ import annotations

from typing import Any


EXECUTION_API_CONTRACT: dict[str, Any] = {
    "version": "1.0.0",
    "base_path": "/api/v1/external-staging-provisioning-execution",
    "real_execution_allowed": False,
    "endpoints": [
        {
            "path": "/status",
            "method": "GET",
            "mutates": False,
            "description": "整体供给执行状态（0/8，apply gate 态，无伪造标记）",
        },
        {
            "path": "/resources",
            "method": "GET",
            "mutates": False,
            "description": "8 资源 BOM 与逐资源状态机快照",
        },
        {
            "path": "/iac-readiness",
            "method": "GET",
            "mutates": False,
            "description": "infrastructure/staging/*.tf 可执行就绪审计",
        },
        {
            "path": "/apply-gate",
            "method": "GET",
            "mutates": False,
            "description": "双钥匙 Apply Gate 状态（永不 GO）",
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
        "POST /resources",
        "PUT /resources/{id}",
        "DELETE /resources/{id}",
        "any endpoint that provisions/registers/connects/isolates a real resource",
    ],
    "note": "AI 不提供任何 mutating 端点；真实 apply 须真人双钥匙在带外执行。",
}


__all__ = ["EXECUTION_API_CONTRACT"]
