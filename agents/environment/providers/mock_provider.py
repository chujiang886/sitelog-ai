"""Mock Environment 数据 Provider（Phase 2.2 / 2.2.1，ADR-2.2.1 §11）。

红线 R-01 三重锁（防 mock 数据被误当真实数据固化）：
1. 样本值显式携带 ``__mock__`` 标记（source / raw_ref / 文本值全部可辨识）；
2. ``real_data=False`` 恒定——下游据此禁止标 ``measured``；
3. **不使用任何真实城市的真实风况数值**：坐标 / 风速为明显合成值。

用途：CI 与测试注入（local_ci.sh 全程零外网请求）；结构与真实 Provider
完全同构，供 Agent 集成路径做契约级验证。
"""

from __future__ import annotations

from datetime import datetime, timezone

from agents.environment.providers.base import (
    GeoProvider,
    GeoResult,
    WeatherProvider,
    WindClimate,
)


MOCK_PROVIDER_NAME: str = "mock"


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO8601 for fetched_at fields."""

    return datetime.now(timezone.utc).isoformat()


class MockGeoProvider(GeoProvider):
    """结构合法的固定样本地理编码（合成值，非任何真实地点）。"""

    name: str = MOCK_PROVIDER_NAME

    async def geocode(self, address: str) -> GeoResult:
        """Return a synthetic, clearly-marked mock geocoding sample."""

        return GeoResult(
            lat=1.23,   # 合成坐标，非真实地点
            lng=4.56,
            province="__mock__省",
            city="__mock__市",
            district="__mock__区",
            source=MOCK_PROVIDER_NAME,
            fetched_at=_now_iso(),
            raw_ref="mock:geo:v1:__mock__",
            ok=True,
            real_data=False,
        )


class MockWeatherProvider(WeatherProvider):
    """结构合法的固定样本风况统计（合成值，非任何真实城市的真实风况）。"""

    name: str = MOCK_PROVIDER_NAME

    async def wind_climate(self, lat: float, lng: float) -> WindClimate:
        """Return a synthetic, clearly-marked mock wind-climate sample."""

        return WindClimate(
            prevailing_wind="__mock__NE",
            avg_wind_speed_ms=9.99,  # 合成风速样本，非真实统计
            stat_years="__mock__",
            source=MOCK_PROVIDER_NAME,
            fetched_at=_now_iso(),
            raw_ref="mock:wind:v1:__mock__",
            ok=True,
            real_data=False,
        )


__all__ = [
    "MOCK_PROVIDER_NAME",
    "MockGeoProvider",
    "MockWeatherProvider",
]
