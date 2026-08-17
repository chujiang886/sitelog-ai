"""Phase 3.9.14 —— Failure / Recovery / Rollback 计划（Task 31，fail-closed）。

``FailureRecoveryRollbackPlan`` 描述 External Staging 的故障演练与恢复/回滚形态：
- 合成故障注入（``inject_synthetic_fault_local``，**允许**的本地预生产动作）；
- 恢复模拟（``simulate_recovery_local``，允许）；
- 回滚计划（plan-only）：staging 回滚可由人工在授权后执行，但 **production 回滚永远禁止**
  （``rollback_production`` 在 ``FORBIDDEN_PRODUCTION_ACTIONS`` 内，执行边界恒拒）。

fail-closed：本模块**绝不**发起真实故障注入/恢复/回滚；所有步骤均为计划描述。
production 回滚令牌在任何情况下都被执行边界拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agents.staging_runtime.execution_scope import (
    StagingExecutionScope,
    FORBIDDEN_PRODUCTION_ACTIONS,
)

from .identity import external_staging_identity


class RecoveryStepKind(str, Enum):
    """恢复/回滚步骤种类（plan-only，绝不真实执行）。"""

    SYNTHETIC_FAULT_INJECTION = "synthetic_fault_injection"
    SIMULATE_RECOVERY = "simulate_recovery"
    ROLLBACK_PLAN = "rollback_plan"


@dataclass(frozen=True)
class RecoveryPlanStep:
    """单条恢复/回滚计划步骤（描述型）。"""

    order: int
    kind: RecoveryStepKind
    action: str
    permitted_by_scope: bool  # 执行边界是否允许（production 类恒 False）
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "kind": self.kind.value,
            "action": self.action,
            "permitted_by_scope": self.permitted_by_scope,
            "detail": self.detail,
        }


@dataclass
class FailureRecoveryRollbackReport:
    """Failure/Recovery/Rollback 汇总（structured，fail-closed）。"""

    passed: bool
    production_rollback_forbidden: bool
    allowed_local_steps: int
    is_production: bool
    real_apply_allowed: bool
    steps: tuple[RecoveryPlanStep, ...] = field(default_factory=tuple)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "production_rollback_forbidden": self.production_rollback_forbidden,
            "allowed_local_steps": self.allowed_local_steps,
            "is_production": self.is_production,
            "real_apply_allowed": self.real_apply_allowed,
            "steps": [s.to_dict() for s in self.steps],
            "generated_at": self.generated_at,
        }


class FailureRecoveryRollbackPlan:
    """External Staging 故障/恢复/回滚计划（fail-closed，plan-only）。"""

    def __init__(self, identity=None) -> None:
        self._identity = identity or external_staging_identity()
        self._scope = StagingExecutionScope(self._identity)

    def build(self) -> FailureRecoveryRollbackReport:
        steps: list[RecoveryPlanStep] = []

        # 1. 合成故障注入（允许）
        steps.append(
            RecoveryPlanStep(
                order=1,
                kind=RecoveryStepKind.SYNTHETIC_FAULT_INJECTION,
                action="inject_synthetic_fault_local",
                permitted_by_scope=self._scope.is_permitted("inject_synthetic_fault_local"),
                detail="在本地预生产注入合成故障，不波及生产；仅验证故障检测与隔离。",
            )
        )

        # 2. 恢复模拟（允许）
        steps.append(
            RecoveryPlanStep(
                order=2,
                kind=RecoveryStepKind.SIMULATE_RECOVERY,
                action="simulate_recovery_local",
                permitted_by_scope=self._scope.is_permitted("simulate_recovery_local"),
                detail="本地预生产模拟恢复路径，不连接真实生产数据。",
            )
        )

        # 3. 回滚计划（plan-only）：staging 回滚可规划，但本阶段仅描述
        steps.append(
            RecoveryPlanStep(
                order=3,
                kind=RecoveryStepKind.ROLLBACK_PLAN,
                action="plan_staging_rollback",
                permitted_by_scope=True,
                detail="规划 staging 回滚步骤（供人工在授权后执行）；本阶段仅描述，不执行。",
            )
        )

        # 负向：production 回滚永远禁止
        prod_rollback_forbidden = not self._scope.is_permitted("rollback_production")
        assert "rollback_production" in FORBIDDEN_PRODUCTION_ACTIONS

        allowed = sum(1 for s in steps if s.permitted_by_scope)
        passed = (
            prod_rollback_forbidden
            and all(s.permitted_by_scope for s in steps[:2])  # 本地故障/恢复允许
            and self._identity.kind.is_production is False
        )
        return FailureRecoveryRollbackReport(
            passed=passed,
            production_rollback_forbidden=prod_rollback_forbidden,
            allowed_local_steps=allowed,
            is_production=self._identity.kind.is_production,
            real_apply_allowed=False,
            steps=tuple(steps),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "RecoveryStepKind",
    "RecoveryPlanStep",
    "FailureRecoveryRollbackReport",
    "FailureRecoveryRollbackPlan",
]
