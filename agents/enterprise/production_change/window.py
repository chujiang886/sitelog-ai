"""Phase 3.9.7 变更窗口域（T3）。真实 USER 预约的维护时段（只读登记）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.enterprise.production_change.models import (
    ChangeState,
    ChangeWindow,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reserve_change_window(
    *,
    change_id: str,
    window_start: str,
    window_end: str,
    reserved_by: str,
    created_at: Optional[str] = None,
) -> ChangeWindow:
    """登记一个变更窗口（维护时段预约；不触发任何执行）。"""

    return ChangeWindow(
        change_id=change_id,
        window_start=window_start,
        window_end=window_end,
        reserved_by=reserved_by,
        state=ChangeState.HUMAN_DRAFTED,
        created_at=created_at or _now(),
    )


__all__ = ["reserve_change_window"]
