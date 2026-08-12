"""Phase 3.9.2 人工激活批准契约（Human Activation Approval，T7 / 红线⑥/⑧）。

``HumanActivationApproval`` 是真实人工对 RC 激活的**最终责任签署**结构。它**只能**由
真实人工在外部（API / 线下人类终端）构造并传入；本模块的服务**不提供**任何
构造 / 代签 / 翻转能力。

设计红线（T7 / ② / ③ / ⑥ / ⑧ / ⑩）：
- ``HumanActivationApprovalService._FORBIDDEN`` 含 ``create_human_activation_approval``
  / ``forge_signature`` / ``mark_activation_approved`` / ``auto_sign_activation`` 等，
  一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed）。
- 服务只能 ``record_*``（把已发生的真实人工签署如实审计留痕）与 ``verify_*``
  （只读核对签署是否齐备、是否 GO）；**不**翻转 ``engineering_enabled``。
- 即便 ``decision == GO`` 且四角色齐备，服务也不宣布 Production GO——
  ``ACTIVATED_BY_HUMAN`` 只是"人工已批准"的责任留痕，**激活动作本身**仍由主理人
  在人类终端执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.audit import AuditService
from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
)
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.models import SignoffDecision
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class HumanActivationApprovalStatus(str, Enum):
    """人工激活批准状态（只能源于真实人工）。"""

    AWAITING_HUMAN = "awaiting_human"
    GO_BY_HUMAN = "go_by_human"
    NO_GO_BY_HUMAN = "no_go_by_human"
    NEED_MORE_EVIDENCE_BY_HUMAN = "need_more_evidence_by_human"


@dataclass(frozen=True)
class HumanActivationApproval:
    """真实人工激活批准契约（只读事实）。

    本结构**不在此构造**——``approved_by`` / ``approved_roles`` / ``decision`` 必须来自
    真实人工在外部完成；AI 不得填充（红线⑥/⑧）。
    """

    approval_id: str
    rc_id: str
    version: str
    decision: SignoffDecision  # 真实人工 GO / NO_GO
    approved_by: str  # 真实人工 actor id
    approved_roles: List[str]  # 真实人工签署角色
    approved_at: str
    activation_approved: bool  # 仅当真实人工 GO 且四角色齐备时 True
    note: str = (
        "HUMAN_ACTIVATION_APPROVAL_ONLY: 真实人工责任签署；AI 不构造、不代签；"
        "不翻转 engineering_enabled；激活动作由主理人在人类终端执行"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "rc_id": self.rc_id,
            "version": self.version,
            "decision": self.decision.value,
            "approved_by": self.approved_by,
            "approved_roles": list(self.approved_roles),
            "approved_at": self.approved_at,
            "activation_approved": self.activation_approved,
            "note": self.note,
        }

    @property
    def roles_complete(self) -> bool:
        return set(REQUIRED_SIGNOFF_ROLES).issubset(set(self.approved_roles))

    @property
    def is_valid_go(self) -> bool:
        # 真实人工 GO 且四角色齐备，才具备"已批准"资格；仍不翻转 engineering_enabled。
        return (
            self.decision == SignoffDecision.GO
            and self.roles_complete
            and self.activation_approved
        )


class HumanActivationApprovalService(_RedLineForbiddenMixin):
    """人工激活批准服务（只读留痕 + 只读核对；不构造、不代签、不激活）。

    ``_FORBIDDEN`` 含 ``create_human_activation_approval`` / ``forge_signature`` /
    ``mark_activation_approved`` / ``auto_sign_activation`` / ``open_activation_gate``
    等；任何构造 / 代签 / 翻转调用均 fail-closed。
    """

    _FORBIDDEN = _FREEZE_ACTIVATION_FORBIDDEN

    def __init__(self, *, audit: AuditService) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建人工激活批准服务（红线①）"
            )
        self._audit = audit

    @staticmethod
    def _require_user(actor_id: str) -> None:
        if not actor_id:
            raise EnterpriseRedLineViolationError(
                "人工激活批准审计入口要求真实 USER actor_id（红线⑥/⑧）"
            )

    def record_activation_approval_recorded(
        self,
        *,
        actor_id: str,
        approval_id: str,
        rc_id: str,
        decision: str,
        roles: List[str],
        detail: str = "",
    ) -> Any:
        """把一次已发生的真实人工激活批准如实审计留痕（actor_kind 恒 USER）。

        本方法**不**构造 ``HumanActivationApproval``（那是真实人工在外部完成的）；
        这里仅记录"已发生"的责任事件，并强制 actor 为真实 USER。
        """

        self._require_user(actor_id)
        return self._audit.record_human_activation_approval_recorded(
            record_id=f"haa-{approval_id}",
            actor_id=actor_id,
            action=f"human_activation_approval_{decision}",
            target=rc_id,
            detail=f"decision={decision};roles={','.join(roles)};{detail[:160]}",
            ts=_now(),
        )

    def verify_activation_approval(
        self, *, approval: HumanActivationApproval
    ) -> Dict[str, object]:
        """只读核对真实人工批准是否满足激活前置（不翻转 engineering_enabled）。

        返回 ``{"activation_approved": bool, "roles_complete": bool, "decision": ...}``；
        即便全满足也**不**宣布 Production GO——激活动作由主理人在人类终端执行。
        """

        return {
            "activation_approved": approval.is_valid_go,
            "roles_complete": approval.roles_complete,
            "decision": approval.decision.value,
            "note": "VERIFY_ONLY: 不翻转 engineering_enabled；激活由主理人线下执行",
        }


__all__ = [
    "HumanActivationApprovalStatus",
    "HumanActivationApproval",
    "HumanActivationApprovalService",
]
