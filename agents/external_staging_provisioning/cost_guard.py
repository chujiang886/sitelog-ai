"""Phase 3.9.12 —— 供给成本护栏（Task 30，StagingCostGuard）。

fail-closed 预算护栏：真实供给预估成本超 ``cost_budget``（默认 ¥6000 示意上限，非真实报价）
即阻断 apply（对应 Runbook T21 的「超预算阻断」与容量基线 T23a）。

成本数字均为**示意区间**，用于规划与护栏锚点，不构成任何真实报价/配额承诺。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.bom import ProvisioningBom

# 默认预算上限（¥，示意）。真实预算由责任角色在人工输入表（T20）登记。
DEFAULT_COST_BUDGET = 6000

# 三档容量基线（A 最小可用 / B 推荐 / C 类生产）的**示意月度成本区间下限**（¥）。
# 仅用于护栏与规划，非真实报价。
_CAPACITY_COST_FLOOR = {
    "database": (300, 800, 1500),
    "secret_provider": (0, 50, 100),
    "identity_provider": (0, 200, 500),
    "object_storage": (50, 150, 300),
    "telemetry": (100, 300, 600),
    "alert_sandbox": (0, 50, 100),
    "domain_tls": (0, 100, 200),
    "deployment_target": (500, 1200, 2500),
}


@dataclass
class CostCheckResult:
    """成本护栏检查结果。"""

    within_budget: bool
    estimated_min: float
    budget: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "within_budget": self.within_budget,
            "estimated_min": self.estimated_min,
            "budget": self.budget,
            "detail": self.detail,
        }


class StagingCostGuard:
    """供给成本护栏（fail-closed）。"""

    def __init__(self, budget: float = DEFAULT_COST_BUDGET) -> None:
        self.budget = budget

    def estimate_min(self, bom: ProvisioningBom | None = None) -> float:
        """按 A 档（最小可用）示意成本下限估算 8 资源总月度成本。"""

        bom = bom or ProvisioningBom.build_default()
        total = 0.0
        for e in bom.entries:
            floor = _CAPACITY_COST_FLOOR.get(e.resource_type.value, (0, 0, 0))
            total += float(floor[0])
        return total

    def check(self, estimated: float | None = None, bom: ProvisioningBom | None = None) -> CostCheckResult:
        """检查预估成本是否超预算（fail-closed）。"""

        est = estimated if estimated is not None else self.estimate_min(bom)
        within = est <= self.budget
        detail = (
            f"预估最低成本 ¥{est:.0f} ≤ 预算 ¥{self.budget:.0f}，护栏通过。"
            if within
            else f"预估最低成本 ¥{est:.0f} > 预算 ¥{self.budget:.0f}，护栏阻断 apply。"
        )
        return CostCheckResult(
            within_budget=within, estimated_min=est, budget=self.budget, detail=detail
        )

    def assert_within_budget(self, estimated: float | None = None, bom: ProvisioningBom | None = None) -> None:
        """超预算即抛（fail-closed）。"""

        res = self.check(estimated=estimated, bom=bom)
        if not res.within_budget:
            raise ValueError(res.detail)


__all__ = [
    "DEFAULT_COST_BUDGET",
    "CostCheckResult",
    "StagingCostGuard",
]
