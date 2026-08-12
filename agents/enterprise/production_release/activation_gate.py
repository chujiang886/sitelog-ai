"""Phase 3.9.2 受控激活闸门（Controlled Activation Gate，激活前最后一道受控判定）。

``ControlledActivationGate.evaluate`` 在 RC 冻结检查（``FROZEN``）与激活证据包
（``complete``）之上，做最后一道**受控激活**判定。它只产出三类人工前置终态：

- ``BLOCKED``：任一硬检查失败（冻结漂移 / 治理不完整 / engineering_enabled 为真 / 缺证据）；
- ``PENDING_VERIFICATION``：客观检查全过但真实人工签署仍 PENDING；
- ``READY_FOR_HUMAN_REVIEW``：全过且等待真实人工最终裁决。

红线（T5 / ② / ③ / ⑥ / ⑧ / ⑩）：
- **禁止** ``APPROVED`` / ``AUTO_APPROVED`` / ``ACTIVATED_BY_HUMAN`` 作为 AI 终态；
  即便全部客观检查通过，只要真实人工签署仍 PENDING，闸门也只返回
  ``READY_FOR_HUMAN_REVIEW`` / ``PENDING_VERIFICATION``。
- ``ACTIVATED_BY_HUMAN`` 只能由 ``HumanActivationApprovalService`` 在收到真实人工
  ``GO`` 签署后产出——且**不**翻转 ``engineering_enabled``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

from agents.config_loader import load_engineering_enabled
from agents.enterprise.production_release.activation_evidence import (
    ActivationEvidenceBundle,
)
from agents.enterprise.production_release.freeze_checker import (
    FreezeCheckResult,
    _governance_integrity_ok,
)
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.freeze_manifest import RCFreezeManifest
from agents.enterprise.production_release.release_candidate import (
    RCFreezeStatus,
    ReleaseCandidate,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class ControlledActivationGateStatus(str, Enum):
    """受控激活闸门状态（AI 只产出前四种；ACTIVATED_BY_HUMAN 由人工审批服务产出）。"""

    AWAITING_HUMAN = "awaiting_human"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"
    # 以下仅由 HumanActivationApprovalService 在真实人工 GO 后产出；闸门永不返回。
    ACTIVATED_BY_HUMAN = "activated_by_human"


@dataclass(frozen=True)
class ControlledActivationGateResult:
    """受控激活闸门评估结果（只读事实）。"""

    gate_id: str
    rc_id: str
    status: ControlledActivationGateStatus
    checks: Dict[str, bool] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    evaluated_at: str = ""
    note: str = (
        "CONTROLLED_ACTIVATION_GATE_ONLY: 仅判定受控激活前置态；不激活；"
        "ACTIVATED_BY_HUMAN 只能源于真实人工 GO 签署"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "rc_id": self.rc_id,
            "status": self.status.value,
            "checks": dict(self.checks),
            "missing": list(self.missing),
            "evaluated_at": self.evaluated_at,
            "note": self.note,
        }


class ControlledActivationGate(_RedLineForbiddenMixin):
    """受控激活闸门（fail-closed，只读，永不 AI 自决放行）。"""

    _FORBIDDEN = _FREEZE_ACTIVATION_FORBIDDEN

    def __init__(self, *, check_governance: bool = True) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建受控激活闸门（红线①）"
            )
        self.check_governance = check_governance

    # 闸门评估所需客观检查键（与收口报告 / 测试一一对应）。
    CHECK_KEYS = (
        "engineering_enabled_false",
        "rc_status_frozen_awaiting_human_or_verified",
        "freeze_check_frozen",
        "evidence_bundle_complete",
        "human_signoffs_complete",
        "governance_integrity_9_9",
        "rollback_reference_present",
        "recovery_validation_present",
    )

    def evaluate(
        self,
        *,
        rc: ReleaseCandidate,
        manifest: RCFreezeManifest,
        freeze_result: FreezeCheckResult,
        evidence_bundle: ActivationEvidenceBundle,
        root_dir: str = ".",
    ) -> ControlledActivationGateResult:
        """在 RC 冻结 + 证据包之上判定受控激活前置态。

        返回 ``BLOCKED`` / ``PENDING_VERIFICATION`` / ``READY_FOR_HUMAN_REVIEW``；
        **永不**返回 ``ACTIVATED_BY_HUMAN``（红线②/③/⑩）。
        """

        checks: Dict[str, bool] = {}

        # 1. 红线①：engineering_enabled 必须 False
        checks["engineering_enabled_false"] = load_engineering_enabled() is False

        # 2. RC 状态为冻结待人工 / 已人工核验（REJECTED 视为 blocked）
        checks["rc_status_frozen_awaiting_human_or_verified"] = rc.status in (
            RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN,
            RCFreezeStatus.VERIFIED_BY_HUMAN,
        )

        # 3. 冻结检查 FROZEN
        checks["freeze_check_frozen"] = bool(freeze_result.frozen)

        # 4-5. 证据包齐备 + 真实人工签署齐备
        checks["evidence_bundle_complete"] = bool(evidence_bundle.evidence_complete)
        checks["human_signoffs_complete"] = bool(evidence_bundle.signoffs_complete)

        # 6. 治理完整性 9/9（可选）
        if self.check_governance:
            checks["governance_integrity_9_9"] = _governance_integrity_ok(
                os.path.abspath(root_dir)
            )

        # 7-8. 回滚引用 / 恢复校验齐备
        checks["rollback_reference_present"] = bool(
            evidence_bundle.rollback_reference_present
        )
        checks["recovery_validation_present"] = bool(
            evidence_bundle.recovery_validation_present
        )

        missing = [k for k, v in checks.items() if not v]
        # ``human_signoffs_complete`` 缺失代表"真实人工签署仍待决"，属人工前置态而非
        # 硬失败；硬失败只含冻结漂移 / 治理不完整 / engineering_enabled 为真 / 缺客观
        # 证据 / 缺回滚恢复引用等。两者必须分开判定（红线⑥/⑧/⑩）。
        hard_missing = [k for k in missing if k != "human_signoffs_complete"]

        if hard_missing:
            status = ControlledActivationGateStatus.BLOCKED
        elif not evidence_bundle.is_complete:
            # 客观检查全过，但真实人工签署/证据仍 PENDING → 待核验
            status = ControlledActivationGateStatus.PENDING_VERIFICATION
        else:
            # 全过：仍只给人工前置态，不直接放行（红线②/③/⑩）
            status = ControlledActivationGateStatus.READY_FOR_HUMAN_REVIEW

        return ControlledActivationGateResult(
            gate_id=f"cag-{rc.rc_id}",
            rc_id=rc.rc_id,
            status=status,
            checks=checks,
            missing=missing,
            evaluated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


__all__ = [
    "ControlledActivationGateStatus",
    "ControlledActivationGateResult",
    "ControlledActivationGate",
]
