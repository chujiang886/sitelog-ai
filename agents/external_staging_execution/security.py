"""Phase 3.9.11 —— Execution Security Validator（Task 35）。

请求级安全校验：仅允许 ``external_staging`` 作用域下的 ``read`` / ``human_record``
动作；**禁止**任何真实执行/生产动作（execute / deploy / activate / rollback_execute /
production_write / secret_write）。fail-closed：未知动作默认拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ALLOWED_SCOPES = ("external_staging",)
ALLOWED_ACTIONS = ("read", "human_record")
FORBIDDEN_ACTIONS = (
    "execute",
    "deploy",
    "activate",
    "rollback_execute",
    "production_write",
    "secret_write",
)


@dataclass
class ExecutionSecurityCheckResult:
    """安全校验结果。"""

    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "detail": self.detail}


class ExternalStagingExecutionSecurityValidator:
    """执行请求安全校验器（fail-closed）。"""

    def validate_request(
        self,
        *,
        scope: str,
        actor: str,
        action: str,
        is_production_action: bool = False,
    ) -> ExecutionSecurityCheckResult:
        if scope not in ALLOWED_SCOPES:
            return ExecutionSecurityCheckResult(
                False, f"scope {scope!r} 不允许（仅 {ALLOWED_SCOPES}）。"
            )
        if action in FORBIDDEN_ACTIONS or is_production_action:
            return ExecutionSecurityCheckResult(
                False, f"action {action!r} 为禁止的真实执行/生产动作（红线）。"
            )
        if action not in ALLOWED_ACTIONS:
            return ExecutionSecurityCheckResult(
                False, f"action {action!r} 不在允许集 {ALLOWED_ACTIONS}（fail-closed 默认拒绝）。"
            )
        return ExecutionSecurityCheckResult(
            True,
            f"请求合法：scope={scope}, action={action}（只读/人工登记，无真实执行）。",
        )


__all__ = [
    "ALLOWED_SCOPES",
    "ALLOWED_ACTIONS",
    "FORBIDDEN_ACTIONS",
    "ExecutionSecurityCheckResult",
    "ExternalStagingExecutionSecurityValidator",
]
