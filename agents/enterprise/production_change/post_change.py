"""Phase 3.9.7 变更后验证域（T8）。描述待验证项与状态；AI 不得把
PENDING_VERIFICATION 自动提升为 VERIFIED_BY_HUMAN（红线⑩）。``verified_by`` 仅可
填入真实 USER actor_id。
"""

from __future__ import annotations

from typing import Optional

from agents.enterprise.production_change.models import (
    ChangeVerificationStatus,
    PostChangeVerification,
)


def register_post_change_verification(
    *,
    verification_id: str,
    change_id: str,
    verification_type: str,
    status: ChangeVerificationStatus = ChangeVerificationStatus.PENDING_VERIFICATION,
    verified_by: Optional[str] = None,
    detail: str = "",
) -> PostChangeVerification:
    """登记一项变更后验证（AI 路径恒 PENDING_VERIFICATION；不替人验证）。"""

    return PostChangeVerification(
        verification_id=verification_id,
        change_id=change_id,
        verification_type=verification_type,
        status=status,
        verified_by=verified_by,
        detail=detail,
    )


__all__ = ["register_post_change_verification"]
