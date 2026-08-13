"""Phase 3.9.7 变更前预检域（T4）。AI 只产出 READY_FOR_HUMAN_REVIEW / BLOCKED /
PENDING_VERIFICATION；绝不产出 APPROVED / AUTO_APPROVED / ENGINEERING_APPROVED。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from agents.enterprise.production_change.models import (
    ChangePreflightResult,
    ChangePreflightStatus,
)


def evaluate_change_preflight(
    *,
    checks: Optional[Dict[str, bool]] = None,
    missing: Optional[List[str]] = None,
) -> ChangePreflightResult:
    """评估变更前预检（fail-closed：永不返回 APPROVED）。

    ``READY_FOR_HUMAN_REVIEW`` 仅代表"可供人工评审"，不代表放行。
    """

    checks = checks or {}
    missing = missing or []
    if missing:
        status = ChangePreflightStatus.BLOCKED
    elif all(checks.values()):
        status = ChangePreflightStatus.READY_FOR_HUMAN_REVIEW
    else:
        status = ChangePreflightStatus.PENDING_VERIFICATION
    return ChangePreflightResult(status=status, checks=checks, missing=missing)


__all__ = ["evaluate_change_preflight"]
