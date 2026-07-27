"""Environment 数据 Provider 抽象层（Phase 2.2 / 2.2.1，ADR-2.2.1）。

三模式：disabled（默认，零行为变化）/ mock（CI 零外网）/ 真实源（注册表
扩展位，ADR-02 厂商批准后接入）。所有结果强制携带 source / fetched_at /
raw_ref 溯源；非真实数据（real_data=False）永远保持 pending_verification。
"""

from agents.environment.providers.base import (
    GeoProvider,
    GeoResult,
    WeatherProvider,
    WindClimate,
)
from agents.environment.providers.factory import (
    DISABLED_PROVIDER_NAME,
    EnvironmentProviderConfigError,
    build_geo_provider,
    build_weather_provider,
    register_geo_provider,
    register_weather_provider,
)
from agents.environment.providers.mock_provider import (
    MOCK_PROVIDER_NAME,
    MockGeoProvider,
    MockWeatherProvider,
)

__all__ = [
    "DISABLED_PROVIDER_NAME",
    "EnvironmentProviderConfigError",
    "GeoProvider",
    "GeoResult",
    "MOCK_PROVIDER_NAME",
    "MockGeoProvider",
    "MockWeatherProvider",
    "WeatherProvider",
    "WindClimate",
    "build_geo_provider",
    "build_weather_provider",
    "register_geo_provider",
    "register_weather_provider",
]
