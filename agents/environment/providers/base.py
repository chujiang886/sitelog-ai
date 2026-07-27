"""Environment 数据 Provider 抽象契约（Phase 2.2 / 2.2.1，ADR-2.2.1 §2）。

设计要点：
- 复刻 2.1.6 LLM Provider 解耦模式：抽象基类 + 配置驱动工厂 + mock/disabled；
- 所有数据结果强制携带三溯源字段 ``source`` / ``fetched_at`` / ``raw_ref``，
  缺一即构造失败（fail-fast，与 ``agents.base.Evidence`` 同风格）；
- ``real_data`` 真实性标记：只有真实外部源返回 ``True``；mock / 推理数据
  永远为 ``False``，且下游只有 ``real_data=True`` 才允许字段级 ``measured``
  （防编造红线 R-01 的第一重锁）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


def _require(value: str, field_name: str) -> None:
    """Reject blank provenance fields instead of silently losing traceability."""

    if not value or not value.strip():
        raise ValueError(f"provider result field '{field_name}' must not be empty")


@dataclass(frozen=True, slots=True)
class GeoResult:
    """地理编码结果（地址 → 坐标/行政区划），含完整溯源。"""

    lat: float | None
    lng: float | None
    province: str | None
    city: str | None
    district: str | None
    source: str          # 数据源标识，如 "mock" / <ADR-02 批准后的真实源名>
    fetched_at: str      # ISO8601 获取时间
    raw_ref: str         # 原始响应留痕引用（脱敏后可进 evidence）
    ok: bool
    real_data: bool = False  # 只有真实外部源返回 True；mock 恒 False
    error: str | None = None

    def __post_init__(self) -> None:
        """Enforce the ADR-2.2.1 provenance contract on every result."""

        _require(self.source, "source")
        _require(self.fetched_at, "fetched_at")
        _require(self.raw_ref, "raw_ref")


@dataclass(frozen=True, slots=True)
class WindClimate:
    """多年风况统计结果（非实时预报），含完整溯源。"""

    prevailing_wind: str | None      # 多年统计主导风向
    avg_wind_speed_ms: float | None  # 多年平均风速（m/s）
    stat_years: str | None           # 统计年限描述
    source: str
    fetched_at: str
    raw_ref: str
    ok: bool
    real_data: bool = False
    error: str | None = None

    def __post_init__(self) -> None:
        """Enforce the ADR-2.2.1 provenance contract on every result."""

        _require(self.source, "source")
        _require(self.fetched_at, "fetched_at")
        _require(self.raw_ref, "raw_ref")


class GeoProvider(ABC):
    """地理编码 Provider 抽象基类（数据缺口 G1）。"""

    name: str = "abstract"

    @abstractmethod
    async def geocode(self, address: str) -> GeoResult:
        """Resolve an address into coordinates and administrative divisions."""

        raise NotImplementedError


class WeatherProvider(ABC):
    """风况统计 Provider 抽象基类（数据缺口 G3，多年统计而非实时预报）。"""

    name: str = "abstract"

    @abstractmethod
    async def wind_climate(self, lat: float, lng: float) -> WindClimate:
        """Fetch long-term wind statistics for the given coordinates."""

        raise NotImplementedError


__all__ = [
    "GeoProvider",
    "GeoResult",
    "WeatherProvider",
    "WindClimate",
]
