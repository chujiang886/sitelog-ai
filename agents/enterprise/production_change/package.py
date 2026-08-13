"""Phase 3.9.7 受控变更包域（T25）。描述变更材料与引用（材料 ≠ 执行）。

``ControlledChangePackage.simulated_only`` 恒 ``True``：本包仅供人工评审，绝不触发真实
变更执行。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_change.models import (
    ChangeDecisionDraft,
    ChangeEvidence,
    ChangePlan,
    ChangePreflightResult,
    ChangeRequest,
    ChangeRollbackReference,
    ChangeSimulationResult,
    ControlledChangePackage,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ControlledChangePackageBuilder:
    """受控变更包构建器（只读汇总；simulated_only 恒 True）。"""

    def build_package(
        self,
        *,
        package_id: str,
        change: ChangeRequest,
        plan: Optional[ChangePlan] = None,
        preflight: Optional[ChangePreflightResult] = None,
        rollback_reference: Optional[ChangeRollbackReference] = None,
        evidence: Optional[List[ChangeEvidence]] = None,
        simulation: Optional[ChangeSimulationResult] = None,
        decision_draft: Optional[ChangeDecisionDraft] = None,
    ) -> ControlledChangePackage:
        contents: Dict[str, Any] = {
            "change_id": change.change_id,
            "title": change.title,
            "execution_mode": change.execution_mode.value,
            "state": change.state.value,
            "change_approved": change.change_approved,
            "plan_reference": plan.plan_reference if plan else None,
            "rollback_plan_reference": (
                plan.rollback_plan_reference if plan else None
            ),
            "preflight_status": preflight.status.value if preflight else None,
            "rollback_reference_present": rollback_reference is not None,
            "evidence_count": len(evidence or []),
            "simulation_is_simulation": (
                simulation.is_simulation if simulation else None
            ),
            "simulation_outcome": simulation.outcome.value if simulation else None,
            "decision_draft_status": (
                decision_draft.status.value if decision_draft else None
            ),
        }
        return ControlledChangePackage(
            package_id=package_id,
            change_id=change.change_id,
            contents=contents,
            simulated_only=True,  # 恒 True
            generated_at=_now(),
        )


def build_change_package(
    *,
    package_id: str,
    change: ChangeRequest,
    plan: Optional[ChangePlan] = None,
    preflight: Optional[ChangePreflightResult] = None,
    rollback_reference: Optional[ChangeRollbackReference] = None,
    evidence: Optional[List[ChangeEvidence]] = None,
    simulation: Optional[ChangeSimulationResult] = None,
    decision_draft: Optional[ChangeDecisionDraft] = None,
) -> ControlledChangePackage:
    return ControlledChangePackageBuilder().build_package(
        package_id=package_id,
        change=change,
        plan=plan,
        preflight=preflight,
        rollback_reference=rollback_reference,
        evidence=evidence,
        simulation=simulation,
        decision_draft=decision_draft,
    )


__all__ = ["ControlledChangePackageBuilder", "build_change_package"]
