"""Phase 3.9.2 受控激活证据包（Activation Evidence Bundle，T6-equivalent for activation）。

``ActivationEvidenceBundle`` 是激活前证据的**只读汇总**结构：它把「冻结清单哈希 /
治理完整性 9/9 / 回滚引用 / 恢复校验 / 真实人工签署角色」归集为一处，并诚实给出
``is_complete``（缺真实人工签署则恒 False）。

设计红线（T6 / ⑥ / ⑧ / ⑩）：
- 本模块**不构造**任何真实人工签署——``human_signoff_roles`` 必须来自真实人工在
  外部（API / 线下）完成时传入；AI 不得编造、不得代签。
- ``is_complete`` 仅在「证据齐备 + 四角色真实签署齐备 + 治理完整 + 回滚/恢复齐备」
  时为真；任一缺失即 False，闸门据此保持 ``PENDING_VERIFICATION`` / ``BLOCKED``。
- 本模块不持有生产状态、不翻转 ``engineering_enabled``、不宣布激活 GO。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from agents.enterprise.production_release.models import EvidenceIntegrityStatus


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 激活前必须由真实人工签署的四类角色（红线⑥/⑧）。
REQUIRED_SIGNOFF_ROLES = (
    "production-owner",
    "release-manager",
    "security-owner",
    "auditor",
)


class ActivationEvidenceStatus(str, Enum):
    """激活证据包状态（AI 只产出 INCOMPLETE / COMPLETE_AWAITING_HUMAN）。"""

    INCOMPLETE = "incomplete"
    COMPLETE_AWAITING_HUMAN = "complete_awaiting_human"


@dataclass(frozen=True)
class ActivationEvidenceBundle:
    """激活前证据包（只读汇总）。

    ``human_signoff_roles`` 仅记录由**真实人工**完成的签署角色；AI 不得填充。
    ``is_complete`` 由事实推导——缺真实人工签署即 False（fail-closed，红线⑧/⑩）。
    """

    bundle_id: str
    rc_id: str
    version: str
    required_evidence_types: List[str]
    provided_evidence_types: List[str]
    human_signoff_roles: List[str]  # 真实人工签署角色（外部传入，不构造）
    freeze_manifest_sha256: Optional[str]
    governance_integrity_passed: bool
    rollback_reference_present: bool
    recovery_validation_present: bool
    integrity_status: EvidenceIntegrityStatus
    generated_at: str
    note: str = (
        "ACTIVATION_EVIDENCE_ONLY: 仅汇总激活前证据；缺真实人工签署则 incomplete；"
        "不激活、不翻转 engineering_enabled、不宣布 GO"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "rc_id": self.rc_id,
            "version": self.version,
            "required_evidence_types": list(self.required_evidence_types),
            "provided_evidence_types": list(self.provided_evidence_types),
            "human_signoff_roles": list(self.human_signoff_roles),
            "freeze_manifest_sha256": self.freeze_manifest_sha256,
            "governance_integrity_passed": self.governance_integrity_passed,
            "rollback_reference_present": self.rollback_reference_present,
            "recovery_validation_present": self.recovery_validation_present,
            "integrity_status": self.integrity_status.value,
            "generated_at": self.generated_at,
            "is_complete": self.is_complete,
            "status": self.status.value,
            "note": self.note,
        }

    @property
    def evidence_complete(self) -> bool:
        """必需证据类型是否全部提供（仅比对既有事实，不提升状态）。"""
        return set(self.required_evidence_types).issubset(
            set(self.provided_evidence_types)
        )

    @property
    def signoffs_complete(self) -> bool:
        """必须由真实人工完成的四角色签署是否齐备，AI 无法代填（红线⑥/⑧）。"""
        return set(REQUIRED_SIGNOFF_ROLES).issubset(set(self.human_signoff_roles))

    @property
    def is_complete(self) -> bool:
        """激活证据是否齐备：证据 + 真实人工签署 + 治理完整 + 回滚/恢复齐备。

        缺真实人工签署（``human_signoff_roles`` 为空）即恒 False（fail-closed）。
        """
        return (
            self.evidence_complete
            and self.signoffs_complete
            and self.governance_integrity_passed
            and self.rollback_reference_present
            and self.recovery_validation_present
            and self.integrity_status != EvidenceIntegrityStatus.TAMPERED
        )

    @property
    def status(self) -> ActivationEvidenceStatus:
        return (
            ActivationEvidenceStatus.COMPLETE_AWAITING_HUMAN
            if self.is_complete
            else ActivationEvidenceStatus.INCOMPLETE
        )


def build_activation_evidence_bundle(
    *,
    bundle_id: str,
    rc_id: str,
    version: str,
    required_evidence_types: List[str],
    provided_evidence_types: List[str],
    # 真实人工签署角色必须来自外部（API / 线下），AI 不得编造。
    human_signoff_roles: List[str],
    freeze_manifest_sha256: Optional[str] = None,
    governance_integrity_passed: bool = False,
    rollback_reference_present: bool = False,
    recovery_validation_present: bool = False,
    integrity_status: EvidenceIntegrityStatus = EvidenceIntegrityStatus.PENDING,
) -> ActivationEvidenceBundle:
    """构建激活前证据包（只读汇总；不构造真实人工签署）。

    ``human_signoff_roles`` 为空 → ``is_complete`` 恒 False（fail-closed）。
    """

    return ActivationEvidenceBundle(
        bundle_id=bundle_id,
        rc_id=rc_id,
        version=version,
        required_evidence_types=list(required_evidence_types),
        provided_evidence_types=list(provided_evidence_types),
        human_signoff_roles=list(human_signoff_roles),
        freeze_manifest_sha256=freeze_manifest_sha256,
        governance_integrity_passed=governance_integrity_passed,
        rollback_reference_present=rollback_reference_present,
        recovery_validation_present=recovery_validation_present,
        integrity_status=integrity_status,
        generated_at=_now(),
    )


__all__ = [
    "REQUIRED_SIGNOFF_ROLES",
    "ActivationEvidenceStatus",
    "ActivationEvidenceBundle",
    "build_activation_evidence_bundle",
]
