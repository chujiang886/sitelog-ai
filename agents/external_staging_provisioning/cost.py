"""Phase 3.9.13 —— Plan-only 成本估算（cost，T17-T20 支撑）。

零真实资源场景：成本估算为 0，且明确标注「未产生任何真实计费」。
禁止给出「已发生成本」或「已下单」之类的伪造表述。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlanOnlyCost:
    currency: str = "CNY"
    estimated_monthly: float = 0.0
    billing_status: str = "no_real_resource_provisioned"
    note: str = "plan-only; AI did not provision any billable resource"

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "estimated_monthly": self.estimated_monthly,
            "billing_status": self.billing_status,
            "note": self.note,
        }


def estimate_plan_only_cost() -> dict[str, Any]:
    """返回 plan-only 成本估算（恒为 0，无真实计费）。"""

    return PlanOnlyCost().to_dict()


__all__ = ["PlanOnlyCost", "estimate_plan_only_cost"]
