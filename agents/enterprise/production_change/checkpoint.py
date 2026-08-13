"""Phase 3.9.7 变更检查点域（T5）。真实 USER 在执行过程中记录的里程碑（只读留痕）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.enterprise.production_change.models import ChangeCheckpoint


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_change_checkpoint(
    *,
    checkpoint_id: str,
    change_id: str,
    recorded_by: str,
    note: str = "",
    timestamp: Optional[str] = None,
) -> ChangeCheckpoint:
    """记录一个变更检查点（人工留痕；不触发任何动作）。"""

    return ChangeCheckpoint(
        checkpoint_id=checkpoint_id,
        change_id=change_id,
        recorded_by=recorded_by,
        note=note,
        timestamp=timestamp or _now(),
    )


__all__ = ["record_change_checkpoint"]
