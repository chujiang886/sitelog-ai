"""Rollback Handler（Phase 3.2 Sprint 3.2.5-B）。

落地 Sprint 3.2.5-A 回滚设计：当灰度出现审核错误 / 参数错误 / 链路异常时，
快速将受影响的接口或全局工程审核**恢复为 pending_verification**。

关键不变量（红线）：
- 回滚**只翻转灰度配置开关**（接口级 ``enabled`` / 全局 ``default_enabled``），
  不修改任何历史 ``review_log``（审核链 append-only 不可篡改）；
- 恢复语义：回滚后相关接口不再允许 ``engineering_approved``，结果回落 pending；
- 支持 ``snapshot`` / ``restore``，便于"回滚的回滚"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.engineering.gray_release import GrayReleaseConfig


@dataclass
class RollbackHandler:
    """灰度回滚处理器（操作 GrayReleaseConfig，不触碰 review_log）。"""

    config: GrayReleaseConfig
    _snapshot: dict[str, Any] = field(default_factory=dict, repr=False)

    def snapshot(self) -> None:
        """保存当前可回滚状态（灰度条目 enabled + default_enabled）。"""

        self._snapshot = {
            "default_enabled": self.config.default_enabled,
            "entries": {
                name: entry.enabled for name, entry in self.config.entries.items()
            },
        }

    def _ensure_snapshot(self) -> None:
        if not self._snapshot:
            self.snapshot()

    def close_interface(self, interface: str) -> None:
        """接口级关闭：将该接口灰度 ``enabled`` 置 False（恢复 pending_verification）。"""

        self._ensure_snapshot()
        entry = self.config.entries.get((interface or "").strip())
        if entry is not None:
            entry.enabled = False

    def close_global(self) -> None:
        """全局关闭（熔断）：强制所有接口拒绝工程审核（恢复 pending_verification）。"""

        self._ensure_snapshot()
        self.config.default_enabled = False
        for entry in self.config.entries.values():
            entry.enabled = False

    def restore(self) -> None:
        """从快照恢复（回滚的回滚）；不触碰 review_log。"""

        if not self._snapshot:
            return
        self.config.default_enabled = bool(self._snapshot.get("default_enabled", False))
        for name, enabled in self._snapshot.get("entries", {}).items():
            entry = self.config.entries.get(name)
            if entry is not None:
                entry.enabled = bool(enabled)


__all__ = ["RollbackHandler"]
