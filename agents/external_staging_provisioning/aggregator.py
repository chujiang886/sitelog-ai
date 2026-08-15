"""Phase 3.9.13 —— Partial Progress Aggregator（T30-T35）。

分项计数（不掩盖）：configured / provisioned / registered / connected / isolated /
qualified。真实资源未提供时全 0/8。
禁止用单一百分比掩盖分项缺口。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    ProvisioningStateRegistry,
    ResourceProvisioningState,
)


@dataclass
class PartialProgress:
    total: int = 8
    configured: int = 0
    provisioned: int = 0
    registered: int = 0
    connected: int = 0
    isolated: int = 0
    qualified: int = 0

    def ratios(self) -> dict[str, str]:
        t = self.total or 1
        return {
            "configured": f"{self.configured}/{self.total}",
            "provisioned": f"{self.provisioned}/{self.total}",
            "registered": f"{self.registered}/{self.total}",
            "connected": f"{self.connected}/{self.total}",
            "isolated": f"{self.isolated}/{self.total}",
            "qualified": f"{self.qualified}/{self.total}",
        }

    def any_real_progress(self) -> bool:
        return any(v > 0 for v in (
            self.configured, self.provisioned, self.registered,
            self.connected, self.isolated, self.qualified,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "counts": {
                "configured": self.configured,
                "provisioned": self.provisioned,
                "registered": self.registered,
                "connected": self.connected,
                "isolated": self.isolated,
                "qualified": self.qualified,
            },
            "ratios": self.ratios(),
            "any_real_progress": self.any_real_progress(),
            "single_pct_hides_gaps": False,
        }


class PartialProgressAggregator:
    """分项进度聚合器（fail-closed，不复盖缺口）。"""

    def aggregate(self, registry: ProvisioningStateRegistry) -> PartialProgress:
        p = PartialProgress(total=len(registry._machines))
        for m in registry._machines.values():
            s = m.state
            if s in (
                ResourceProvisioningState.INPUT_RECEIVED,
                ResourceProvisioningState.REFERENCE_VALIDATED,
                ResourceProvisioningState.PLAN_READY,
                ResourceProvisioningState.PLAN_VALIDATED,
                ResourceProvisioningState.HUMAN_AUTHORIZATION_PENDING,
                ResourceProvisioningState.AUTHORIZED_FOR_STAGING_APPLY,
                ResourceProvisioningState.PROVISIONING,
                ResourceProvisioningState.PROVISIONED,
                ResourceProvisioningState.REGISTERED,
                ResourceProvisioningState.CONNECTIVITY_VERIFIED,
                ResourceProvisioningState.ISOLATION_VERIFIED,
                ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
            ):
                p.configured += 1
            if s in (
                ResourceProvisioningState.PROVISIONED,
                ResourceProvisioningState.REGISTERED,
                ResourceProvisioningState.CONNECTIVITY_VERIFIED,
                ResourceProvisioningState.ISOLATION_VERIFIED,
                ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
            ):
                p.provisioned += 1
            if s in (
                ResourceProvisioningState.REGISTERED,
                ResourceProvisioningState.CONNECTIVITY_VERIFIED,
                ResourceProvisioningState.ISOLATION_VERIFIED,
                ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
            ):
                p.registered += 1
            if s in (
                ResourceProvisioningState.CONNECTIVITY_VERIFIED,
                ResourceProvisioningState.ISOLATION_VERIFIED,
                ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
            ):
                p.connected += 1
            if s in (
                ResourceProvisioningState.ISOLATION_VERIFIED,
                ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING,
            ):
                p.isolated += 1
            if s is ResourceProvisioningState.QUALIFIED_EXTERNAL_STAGING:
                p.qualified += 1
        return p


__all__ = ["PartialProgress", "PartialProgressAggregator"]
