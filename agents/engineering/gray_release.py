"""Gray Release 配置结构（Phase 3.2 Sprint 3.2.5-B）。

落地 Sprint 3.2.5-A 灰度策略设计：在工程审核闭环（``engineering_enabled`` 全局闸门）
之上叠加 per-interface 灰度白名单层。

关键不变量（红线）：
- 全局 ``orchestrator.engineering_enabled=false`` 时，无论灰度配置如何，
  ``is_interface_gray_allowed`` **恒返回 False**（不可绕过全局闸门）；
- 灰度配置 ``enabled`` 默认 False（保守）；
- 本模块不读取/写入任何真实工程数值，仅处理标识符与配置布尔。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from agents.config_loader import load_engineering_enabled


DEFAULT_GRAY_RELEASE_PATH: Path = (
    Path(__file__).resolve().parent / "gray_release.json"
)

SCHEMA_VERSION: str = "1.0"


@dataclass
class GrayReleaseEntry:
    """单接口灰度条目。"""

    interface: str
    enabled: bool = False
    allowed_project_tags: list[str] = field(default_factory=list)
    rollout_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "interface": self.interface,
            "enabled": self.enabled,
            "allowed_project_tags": list(self.allowed_project_tags),
            "rollout_pct": self.rollout_pct,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GrayReleaseEntry":
        return cls(
            interface=str(data.get("interface", "")),
            enabled=bool(data.get("enabled", False)),
            allowed_project_tags=list(data.get("allowed_project_tags", []) or []),
            rollout_pct=float(data.get("rollout_pct", 0.0) or 0.0),
        )


@dataclass
class GrayReleaseConfig:
    """灰度总配置。"""

    entries: dict[str, GrayReleaseEntry] = field(default_factory=dict)
    default_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "default_enabled": self.default_enabled,
            "entries": [e.to_dict() for e in self.entries.values()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GrayReleaseConfig":
        cfg = cls(default_enabled=bool(data.get("default_enabled", False)))
        for item in data.get("entries", []) or []:
            entry = GrayReleaseEntry.from_dict(item)
            if entry.interface:
                cfg.entries[entry.interface] = entry
        return cfg


def load_gray_release_config(
    path: Path | str | None = None,
) -> GrayReleaseConfig:
    """读取灰度配置 JSON；缺失/损坏 → 全 False 的保守配置。"""

    target = Path(path) if path is not None else DEFAULT_GRAY_RELEASE_PATH
    if not target.is_file():
        return GrayReleaseConfig()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return GrayReleaseConfig()
    if not isinstance(raw, Mapping):
        return GrayReleaseConfig()
    return GrayReleaseConfig.from_dict(raw)


def is_interface_gray_allowed(
    config: GrayReleaseConfig,
    interface: str,
    project_tag: str | None = None,
    *,
    engineering_enabled: bool | None = None,
) -> bool:
    """判定某接口在灰度白名单内是否允许工程审核。

    红线闸门：全局 ``engineering_enabled`` 必须为 True，否则恒返回 False
    （禁止绕过全局闸门）。``engineering_enabled`` 缺省由 ``config_loader`` 读取。

    判定顺序：
    1. 全局闸门 false → False；
    2. 取接口条目（缺省用 ``default_enabled``）；
    3. 条目 ``enabled`` false → False；
    4. ``allowed_project_tags`` 非空且 ``project_tag`` 不在其中 → False；
    5. ``rollout_pct <= 0`` → False；
    6. 否则 True。
    """

    if engineering_enabled is None:
        engineering_enabled = load_engineering_enabled()
    if not engineering_enabled:
        return False

    entry = config.entries.get((interface or "").strip())
    if entry is None:
        return bool(config.default_enabled)
    if not entry.enabled:
        return False
    if entry.allowed_project_tags and project_tag not in entry.allowed_project_tags:
        return False
    if entry.rollout_pct <= 0:
        return False
    return True


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_GRAY_RELEASE_PATH",
    "GrayReleaseEntry",
    "GrayReleaseConfig",
    "load_gray_release_config",
    "is_interface_gray_allowed",
]
