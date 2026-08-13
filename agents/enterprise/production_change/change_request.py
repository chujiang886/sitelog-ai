"""Phase 3.9.7 变更请求域（T1）。

仅构造变更请求（HUMAN_DRAFTED），不决策、不执行。``execution_mode`` 仅允许
``HUMAN_MANUAL`` / ``EXTERNAL_CONTROLLED_SYSTEM``，AI 不得把自身标为执行方。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.enterprise.production_change.models import (
    ChangeExecutionMode,
    ChangeRequest,
    ChangeState,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_change_request(
    *,
    change_id: str,
    title: str,
    description: str,
    requested_by: str,
    execution_mode: ChangeExecutionMode = ChangeExecutionMode.HUMAN_MANUAL,
    created_at: Optional[str] = None,
) -> ChangeRequest:
    """构造一条变更请求（AI 只造 HUMAN_DRAFTED；change_approved 恒 False）。"""

    if execution_mode not in (
        ChangeExecutionMode.HUMAN_MANUAL,
        ChangeExecutionMode.EXTERNAL_CONTROLLED_SYSTEM,
    ):
        raise ValueError(
            "execution_mode 仅允许 HUMAN_MANUAL / EXTERNAL_CONTROLLED_SYSTEM；"
            "AI_AUTOMATIC 被禁止（红线③/⑩）"
        )
    return ChangeRequest(
        change_id=change_id,
        title=title,
        description=description,
        requested_by=requested_by,
        execution_mode=execution_mode,
        state=ChangeState.HUMAN_DRAFTED,
        change_approved=False,
        created_at=created_at or _now(),
    )


def mark_awaiting_human_review(rc: ChangeRequest) -> ChangeRequest:
    """AI 将变更请求标记为人审待决（AWAITING_HUMAN_REVIEW）；不执行、不批准。"""

    return ChangeRequest(
        change_id=rc.change_id,
        title=rc.title,
        description=rc.description,
        requested_by=rc.requested_by,
        execution_mode=rc.execution_mode,
        state=ChangeState.AWAITING_HUMAN_REVIEW,
        change_approved=False,
        created_at=rc.created_at,
    )


__all__ = ["create_change_request", "mark_awaiting_human_review"]
