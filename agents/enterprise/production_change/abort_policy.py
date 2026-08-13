"""Phase 3.9.7 中止策略域（T6）。明确「自动中止条件 + 必须人工中止」约束（fail-closed）。"""

from __future__ import annotations

from typing import List, Optional

from agents.enterprise.production_change.models import ChangeAbortPolicy


def build_change_abort_policy(
    *,
    change_id: str,
    auto_abort_conditions: Optional[List[str]] = None,
) -> ChangeAbortPolicy:
    """构造中止策略（human_abort_required 恒 True：AI 不得自动中止真实生产变更）。"""

    return ChangeAbortPolicy(
        change_id=change_id,
        auto_abort_conditions=auto_abort_conditions or [],
        human_abort_required=True,
    )


__all__ = ["build_change_abort_policy"]
