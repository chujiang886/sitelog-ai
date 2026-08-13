"""Phase 3.9.7 失败场景评估域（T24）。只读评估某失败场景下是否有缓解措施
（不执行任何回滚 / 修复）。"""

from __future__ import annotations

from typing import Dict, List, Optional

from agents.enterprise.production_change.models import (
    ChangePreflightStatus,
    FailureScenarioEvaluation,
)


def evaluate_failure_scenarios(
    *,
    change_id: str,
    scenarios: List[Dict[str, object]],
    default_status: ChangePreflightStatus = ChangePreflightStatus.PENDING_VERIFICATION,
) -> List[FailureScenarioEvaluation]:
    """评估一组失败场景（只读）。

    每个场景提供 ``scenario_name`` / ``severity`` / ``mitigation_present``；本函数只如实
    记录缓解措施是否存在，**不**执行任何回滚 / 修复动作。
    """

    out: List[FailureScenarioEvaluation] = []
    for idx, sc in enumerate(scenarios):
        name = str(sc.get("scenario_name", f"scenario-{idx}"))
        severity = str(sc.get("severity", "medium"))
        mitigation = bool(sc.get("mitigation_present", False))
        out.append(
            FailureScenarioEvaluation(
                scenario_id=f"fs-{change_id}-{idx}",
                change_id=change_id,
                scenario_name=name,
                severity=severity,
                mitigation_present=mitigation,
                status=default_status,
            )
        )
    return out


__all__ = ["evaluate_failure_scenarios"]
