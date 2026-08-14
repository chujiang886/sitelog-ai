"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Alert & On-call（Task 22-23）。

- Task 22 StagingAlertChannel：描述 staging 告警通道（非生产），拒绝复用 Production
  告警通道（红线：禁止复用 Production alert）。
- Task 23 StagingOnCallSandbox：描述 staging 值班沙箱（非生产），拒绝关联生产值班。

fail-closed：staging 告警/值班绝不连接 production；本模块只描述形态，不推送/不触发。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingAlertingError(Exception):
    """Staging 告警/值班违例（fail-closed）。"""


@dataclass(frozen=True)
class StagingAlertDescriptor:
    channel_present: bool
    is_production: bool = False
    non_production: bool = True
    target: str = "local_staging"

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_present": self.channel_present,
            "is_production": self.is_production,
            "non_production": self.non_production,
            "target": self.target,
        }


class StagingAlertChannel:
    """本地预生产告警通道（只描述形态，绝不连接生产告警）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_alert_refs: Iterable[str] = (),
        staging_channel: str | None = None,
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_alert_refs = frozenset(production_alert_refs)
        self._staging_channel = staging_channel

    def describe(self) -> StagingAlertDescriptor:
        channel = self._staging_channel
        if channel is not None and channel in self._production_alert_refs:
            raise StagingAlertingError(
                "staging 告警通道命中 Production 告警引用集合，拒绝复用"
                "（红线：禁止复用 Production alert）。"
            )
        present = channel is not None and channel != "pending_verification"
        return StagingAlertDescriptor(channel_present=present)

    def trigger(self) -> StagingAlertDescriptor:
        """**永不**触发告警；调用即抛。"""

        raise StagingAlertingError(
            "StagingAlertChannel.trigger() 被调用：系统禁止自动触发告警。"
        )


class StagingOnCallSandbox:
    """本地预生产值班沙箱（只描述形态，绝不关联生产值班）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def describe(self) -> dict[str, Any]:
        return {
            "target": self._identity.kind.value,
            "is_production": self._identity.kind.is_production,
            "non_production": not self._identity.kind.is_production,
            "sandbox": True,
            "note": "staging 值班沙箱为隔离形态，不关联生产值班链路。",
        }


__all__ = [
    "StagingAlertingError",
    "StagingAlertDescriptor",
    "StagingAlertChannel",
    "StagingOnCallSandbox",
]
