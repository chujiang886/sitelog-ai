"""Environment 数据 Provider 工厂（Phase 2.2 / 2.2.1，ADR-2.2.1 §2/§11）。

配置驱动（``agents/config.yaml::environment_data`` 段）：
- ``disabled``（默认）→ ``None``，Agent 走既有 LLM 推理路径，零行为变化；
- ``mock`` → Mock Provider（CI/测试，零外网）；
- 其他名字 → 查注册表；未注册即显式抛错（防错配静默降级）。

真实厂商（ADR-02 DEFERRED）批准后，通过 ``register_geo_provider`` /
``register_weather_provider`` 注册实现类即可接入，工厂零改动。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from agents.environment.providers.base import GeoProvider, WeatherProvider
from agents.environment.providers.mock_provider import (
    MOCK_PROVIDER_NAME,
    MockGeoProvider,
    MockWeatherProvider,
)


DISABLED_PROVIDER_NAME: str = "disabled"

GeoProviderFactory = Callable[[Mapping[str, Any]], GeoProvider]
WeatherProviderFactory = Callable[[Mapping[str, Any]], WeatherProvider]

_GEO_REGISTRY: dict[str, GeoProviderFactory] = {
    MOCK_PROVIDER_NAME: lambda _cfg: MockGeoProvider(),
}
_WEATHER_REGISTRY: dict[str, WeatherProviderFactory] = {
    MOCK_PROVIDER_NAME: lambda _cfg: MockWeatherProvider(),
}


class EnvironmentProviderConfigError(ValueError):
    """Raised when environment_data config names an unregistered provider."""


def register_geo_provider(name: str, factory: GeoProviderFactory) -> None:
    """Register a GeoProvider factory (extension point for approved vendors)."""

    normalized: str = name.strip().lower()
    if not normalized:
        raise ValueError("geo provider name must not be empty")
    _GEO_REGISTRY[normalized] = factory


def register_weather_provider(name: str, factory: WeatherProviderFactory) -> None:
    """Register a WeatherProvider factory (extension point for approved vendors)."""

    normalized: str = name.strip().lower()
    if not normalized:
        raise ValueError("weather provider name must not be empty")
    _WEATHER_REGISTRY[normalized] = factory


def _resolve_name(section: Mapping[str, Any] | None) -> str:
    """Extract the provider name from a config section (missing → disabled)."""

    if not isinstance(section, Mapping):
        return DISABLED_PROVIDER_NAME
    raw: Any = section.get("provider", DISABLED_PROVIDER_NAME)
    name: str = str(raw or DISABLED_PROVIDER_NAME).strip().lower()
    return name or DISABLED_PROVIDER_NAME


def build_geo_provider(cfg: Mapping[str, Any] | None) -> GeoProvider | None:
    """Build the configured GeoProvider (``disabled``/missing → ``None``)."""

    section: Any = (cfg or {}).get("geo") if isinstance(cfg, Mapping) else None
    name: str = _resolve_name(section if isinstance(section, Mapping) else None)
    if name == DISABLED_PROVIDER_NAME:
        return None
    factory: GeoProviderFactory | None = _GEO_REGISTRY.get(name)
    if factory is None:
        raise EnvironmentProviderConfigError(
            f"unregistered geo provider: {name!r} "
            f"(registered: {sorted(_GEO_REGISTRY)})"
        )
    return factory(dict(section) if isinstance(section, Mapping) else {})


def build_weather_provider(cfg: Mapping[str, Any] | None) -> WeatherProvider | None:
    """Build the configured WeatherProvider (``disabled``/missing → ``None``)."""

    section: Any = (cfg or {}).get("weather") if isinstance(cfg, Mapping) else None
    name: str = _resolve_name(section if isinstance(section, Mapping) else None)
    if name == DISABLED_PROVIDER_NAME:
        return None
    factory: WeatherProviderFactory | None = _WEATHER_REGISTRY.get(name)
    if factory is None:
        raise EnvironmentProviderConfigError(
            f"unregistered weather provider: {name!r} "
            f"(registered: {sorted(_WEATHER_REGISTRY)})"
        )
    return factory(dict(section) if isinstance(section, Mapping) else {})


__all__ = [
    "DISABLED_PROVIDER_NAME",
    "EnvironmentProviderConfigError",
    "build_geo_provider",
    "build_weather_provider",
    "register_geo_provider",
    "register_weather_provider",
]
