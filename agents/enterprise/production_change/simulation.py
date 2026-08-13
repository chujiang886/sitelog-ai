"""Phase 3.9.7 受控仿真域（T23）。

**永远是仿真**：``ChangeSimulationResult.is_simulation`` 恒 ``True``（红线⑨）。本模块
**不执行任何真实变更 / 部署 / 回滚 / 应用 / 迁移**，只基于"结构是否齐备"做静态推演，
产出 ``PASS`` / ``FAIL`` / ``BLOCKED`` 描述"在受控仿真环境里观察到的行为"。

任何把仿真结果描述为真实 Production Change / 把仿真当生产验证的动作都被禁名集拦截
（``promote_simulation_to_production`` / ``mark_simulation_as_verified_change`` 已在
``forbidden.py`` 中列为不可达）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.enterprise.production_change.models import (
    ChangeRequest,
    ChangeSimulationOutcome,
    ChangeSimulationResult,
)
from agents.enterprise.production_change.preflight import evaluate_change_preflight
from agents.enterprise.production_change.rollback_reference import (
    ChangeRollbackReference,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_controlled_change_simulation(
    *,
    simulation_id: str,
    change: ChangeRequest,
    rollback_reference: Optional[ChangeRollbackReference] = None,
    preflight_checks: Optional[dict] = None,
    abort_conditions_present: bool = False,
) -> ChangeSimulationResult:
    """运行一次受控（合成）仿真——**绝不执行真实变更**。

    仅基于结构齐备度做静态推演：
    - 缺回滚引用 → BLOCKED；
    - 预检有缺失项 → BLOCKED；
    - 无中止条件 → FAIL（结构上不允许无中止预案的变更）；
    - 其余 → PASS（仅表示"仿真环境里结构齐备"，不代表真实生产可执行）。
    """

    if rollback_reference is None:
        outcome = ChangeSimulationOutcome.BLOCKED
        detail = "仿真：缺少回滚引用，变更不可进入受控窗口"
    else:
        preflight = evaluate_change_preflight(checks=preflight_checks or {})
        if preflight.status.value == "blocked":
            outcome = ChangeSimulationOutcome.BLOCKED
            detail = "仿真：预检存在缺失项"
        elif not abort_conditions_present:
            outcome = ChangeSimulationOutcome.FAIL
            detail = "仿真：缺少中止条件预案，结构上不可放行"
        else:
            outcome = ChangeSimulationOutcome.PASS
            detail = "仿真：结构齐备（仍仅限仿真环境，不执行真实变更）"

    return ChangeSimulationResult(
        simulation_id=simulation_id,
        change_id=change.change_id,
        scenario="controlled_synthetic_change_simulation",
        outcome=outcome,
        is_simulation=True,  # 恒 True
        detail=detail,
    )


__all__ = ["run_controlled_change_simulation"]
