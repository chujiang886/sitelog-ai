"""Phase 3.9.7 变更计划域（T2）。仅描述步骤与回滚预案引用，不执行。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from agents.enterprise.production_change.models import (
    ChangePlan,
    ChangeState,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_change_plan(
    *,
    change_id: str,
    plan_reference: str,
    rollback_plan_reference: str,
    steps: Optional[List[str]] = None,
    created_at: Optional[str] = None,
) -> ChangePlan:
    """构造一份变更计划（材料 ≠ 执行）。"""

    return ChangePlan(
        change_id=change_id,
        plan_reference=plan_reference,
        rollback_plan_reference=rollback_plan_reference,
        steps=steps or [],
        state=ChangeState.HUMAN_DRAFTED,
        created_at=created_at or _now(),
    )


__all__ = ["build_change_plan"]
