"""Partial Aggregator — aggregate 8 resource live states without forgery.

Fail-closed: a missing or non-qualified resource is NEVER hidden or rounded up.
The overall verdict is QUALIFIED only when all 8 resources are in
QUALIFIED_EXTERNAL_STAGING. Until then the count is reported honestly (e.g. 0/8).
"""
from __future__ import annotations

from typing import Dict

from .constants import ALL_RESOURCES, ExternalStagingResource, TERMINAL_SUCCESS
from .resource_state_machine import ResourceLiveStateMachine


class PartialAggregator:
    def __init__(self) -> None:
        self.machines: Dict[ExternalStagingResource, ResourceLiveStateMachine] = {
            r: ResourceLiveStateMachine(resource=r) for r in ALL_RESOURCES
        }

    def snapshot(self) -> Dict[str, str]:
        return {r.value: m.state.value for r, m in self.machines.items()}

    def qualified_count(self) -> int:
        return sum(1 for m in self.machines.values() if m.is_qualified)

    def total(self) -> int:
        return len(self.machines)

    def is_fully_qualified(self) -> bool:
        return self.qualified_count() == self.total()

    def verdict(self) -> str:
        return "QUALIFIED" if self.is_fully_qualified() else "NOT_QUALIFIED"
