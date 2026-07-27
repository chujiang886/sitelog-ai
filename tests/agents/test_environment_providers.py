"""Verify Environment 数据 Provider 抽象层（Phase 2.2 / 2.2.1，ADR-2.2.1）。

覆盖设计 §8 测试矩阵（缓存四态除外——缓存层按 ADR §11 本 Sprint DEFERRED）：
- 契约：GeoResult / WindClimate 强制 source / fetched_at / raw_ref（缺一 fail-fast）；
- 工厂三模式：disabled → None ｜ mock → 实例 ｜ 未注册源名 → 显式抛错；
- 扩展点：register_*_provider 注入自定义实现；
- 命中路径：Provider 成功 → evidence / field_provenance 正确；
- 防编造锁第一重：mock（real_data=False）恒不进实测集、provenance=「mock」；
  真实源（real_data=True）命中 → provenance=「measured」、facts 填充；
- 降级路径：Provider 抛错 → 回落 LLM 推理、gaps 登记、invoke 不抛异常；
- 防编造锁终态：无 Provider 且 LLM 关闭 → 风况字段必须为「不确定」，
  绝不允许任何具体合成值流入真实字段。

CI 全程零外网：mock / 合成 Fake Provider 与 LLM monkeypatch 同构。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.environment.agent import EnvironmentAgent
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
)
from agents.environment.providers.mock_provider import (
    MOCK_PROVIDER_NAME,
    MockGeoProvider,
    MockWeatherProvider,
)


# --------------------------------------------------------------------------- #
# 工具：把 LLM 摆成「成功返回固定 JSON」的 monkeypatch                       #
# --------------------------------------------------------------------------- #


def _patch_llm_success(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    """让 EnvironmentAgent 的 LLM 调用成功返回 ``payload``（不触真实网络）。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda *a, **k: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )
    fake_response = SimpleNamespace(content=json.dumps(payload), model="qwen-test")

    async def _fake_route(_request):
        return fake_response, [
            SimpleNamespace(
                provider_name="track_a",
                track="track_a",
                response=fake_response,
                error=None,
                latency_ms=1,
                pending_verification=False,
            )
        ]

    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda *a, **k: SimpleNamespace(route=_fake_route, aclose=lambda: asyncio.sleep(0)),
    )


def _patch_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 LLM 判为关闭（invoke 走占位路径）。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda *a, **k: {
            "enabled": False,
            "track_a": {},
            "track_b": {},
        },
    )


_LLM_PAYLOAD: dict = {
    "climate_zone": "夏热冬暖地区",
    "prevailing_wind": "东南",
    "solar_exposure": "西晒明显",
    "noise_level_hint": "中",
    "regulatory_hints": ["阳台封装需符合地方管理条例"],
    "regional_material_preference": "断桥铝为主",
    "summary": "汕头沿海，夏热冬暖、东南风主导、西晒明显。",
}


# --------------------------------------------------------------------------- #
# 测试用 Fake Provider（真实源同构，real_data=True）                          #
# --------------------------------------------------------------------------- #


class _RealWeatherProvider(WeatherProvider):
    """模拟已批准真实风况源（real_data=True）——验证 measured 分类路径。"""

    name: str = "fake-real"

    async def wind_climate(self, lat: float, lng: float) -> WindClimate:
        return WindClimate(
            prevailing_wind="SE",
            avg_wind_speed_ms=3.2,
            stat_years="1991-2020",
            source="fake-real",
            fetched_at="2026-07-27T00:00:00Z",
            raw_ref="fake:wind:v1:real",
            ok=True,
            real_data=True,
        )


class _RealGeoProvider(GeoProvider):
    """模拟已批准真实地理编码源（real_data=True）。"""

    name: str = "fake-real-geo"

    async def geocode(self, address: str) -> GeoResult:
        return GeoResult(
            lat=23.35,
            lng=116.68,
            province="广东省",
            city="汕头市",
            district="金平区",
            source="fake-real-geo",
            fetched_at="2026-07-27T00:00:00Z",
            raw_ref="fake:geo:v1:real",
            ok=True,
            real_data=True,
        )


class _FailingWeatherProvider(WeatherProvider):
    """永远抛错的 Provider——验证 ADR-03 降级语义（绝不阻断 invoke）。"""

    name: str = "boom"

    async def wind_climate(self, lat: float, lng: float) -> WindClimate:
        raise RuntimeError("forced provider failure")


# --------------------------------------------------------------------------- #
# 契约：强制溯源三字段（fail-fast）                                            #
# --------------------------------------------------------------------------- #


def test_geo_result_requires_provenance_fields() -> None:
    """GeoResult 缺 source / fetched_at / raw_ref 任一即构造失败。"""

    with pytest.raises(ValueError):
        GeoResult(
            lat=1.0, lng=2.0, province="p", city="c", district="d",
            source="", fetched_at="2026-01-01T00:00:00Z", raw_ref="r",
            ok=True,
        )
    with pytest.raises(ValueError):
        GeoResult(
            lat=1.0, lng=2.0, province="p", city="c", district="d",
            source="s", fetched_at="", raw_ref="r", ok=True,
        )
    with pytest.raises(ValueError):
        GeoResult(
            lat=1.0, lng=2.0, province="p", city="c", district="d",
            source="s", fetched_at="2026-01-01T00:00:00Z", raw_ref="", ok=True,
        )


def test_wind_climate_requires_provenance_fields() -> None:
    """WindClimate 缺溯源三字段即构造失败。"""

    with pytest.raises(ValueError):
        WindClimate(
            prevailing_wind="SE", avg_wind_speed_ms=3.0, stat_years="1991-2020",
            source="", fetched_at="2026-01-01T00:00:00Z", raw_ref="r", ok=True,
        )


# --------------------------------------------------------------------------- #
# 工厂三模式 + 扩展点                                                          #
# --------------------------------------------------------------------------- #


def test_factory_disabled_returns_none() -> None:
    """disabled / 缺失 / None → None（Agent 走 LLM 推理，零行为变化）。"""

    assert build_geo_provider(None) is None
    assert build_geo_provider({}) is None
    assert build_geo_provider({"geo": {"provider": DISABLED_PROVIDER_NAME}}) is None
    assert build_weather_provider({"weather": {"provider": "disabled"}}) is None


def test_factory_mock_returns_instance() -> None:
    """mock → 对应 Mock Provider 实例。"""

    geo = build_geo_provider({"geo": {"provider": MOCK_PROVIDER_NAME}})
    assert isinstance(geo, MockGeoProvider)
    weather = build_weather_provider({"weather": {"provider": MOCK_PROVIDER_NAME}})
    assert isinstance(weather, MockWeatherProvider)


def test_factory_unregistered_raises() -> None:
    """未注册真实源名 → 显式抛错（防错配静默降级）。"""

    with pytest.raises(EnvironmentProviderConfigError):
        build_geo_provider({"geo": {"provider": "amap-not-registered"}})
    with pytest.raises(EnvironmentProviderConfigError):
        build_weather_provider({"weather": {"provider": "open-meteo-not-registered"}})


def test_factory_register_extension_point() -> None:
    """register_geo_provider 注入后，工厂可按名构建。"""

    register_geo_provider("tmp-test", lambda _cfg: MockGeoProvider())
    try:
        provider = build_geo_provider({"geo": {"provider": "tmp-test"}})
        assert isinstance(provider, MockGeoProvider)
    finally:
        # 清退测试注册，避免污染注册表。
        from agents.environment.providers.factory import _GEO_REGISTRY

        _GEO_REGISTRY.pop("tmp-test", None)


# --------------------------------------------------------------------------- #
# Mock Provider 结构 + 防编造锁（real_data 恒 False）                         #
# --------------------------------------------------------------------------- #


def test_mock_geo_provider_structure() -> None:
    """MockGeoProvider 返回结构完整、值明显合成、real_data=False。"""

    result = asyncio.run(MockGeoProvider().geocode("广东省汕头市"))
    assert result.ok is True
    assert result.real_data is False
    assert result.source == MOCK_PROVIDER_NAME
    assert result.lat == 1.23 and result.lng == 4.56
    assert result.province.startswith("__mock__")
    assert result.city.startswith("__mock__")
    assert result.district.startswith("__mock__")
    assert result.raw_ref.startswith("mock:geo:")
    assert result.fetched_at  # 非空 ISO 时间戳


def test_mock_weather_provider_structure() -> None:
    """MockWeatherProvider 返回结构完整、值明显合成、real_data=False。"""

    result = asyncio.run(MockWeatherProvider().wind_climate(23.35, 116.68))
    assert result.ok is True
    assert result.real_data is False
    assert result.source == MOCK_PROVIDER_NAME
    assert result.prevailing_wind.startswith("__mock__")
    assert result.avg_wind_speed_ms == 9.99
    assert result.stat_years.startswith("__mock__")
    assert result.raw_ref.startswith("mock:wind:")
    assert result.fetched_at


# --------------------------------------------------------------------------- #
# 命中路径：mock 注入 → provenance=mock，不进实测集                            #
# --------------------------------------------------------------------------- #


def test_agent_mock_providers_injected_provenance_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """注入 mock Provider：成功路径不崩溃、provenance 标记 mock（非 measured）、
    pending_verification 保持 True（ADR-2.2.1 §7）。"""

    _patch_llm_success(monkeypatch, _LLM_PAYLOAD)
    agent = EnvironmentAgent(
        geo_provider=MockGeoProvider(),
        weather_provider=MockWeatherProvider(),
    )
    ctx = AgentContext(
        request_id="env-mock-hit",
        input_data={"address": "广东省汕头市"},  # 无坐标 → 由 mock geocode 补全
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    # 数据来源标识正确。
    assert result.data["data_providers"] == {"geo": "mock", "weather": "mock"}
    # 防编造锁：mock 不标 measured。
    assert result.data["field_provenance"]["prevailing_wind"] == "mock"
    assert result.data["field_provenance"]["geocode"] == "mock"
    assert result.data["field_provenance"]["climate_zone"] == "inferred"
    # mock 命中仍覆盖 LLM 值，但值自带 __mock__ 标记可辨识。
    assert result.data["prevailing_wind"].startswith("__mock__")
    # 关键字段非 measured → 顶层 pending 恒 True。
    assert result.data["pending_verification"] is True
    # 坐标被 mock geocode 补全。
    assert result.data["coordinates"] == {"lat": 1.23, "lng": 4.56}


# --------------------------------------------------------------------------- #
# 命中路径：真实源（real_data=True）→ provenance=measured + facts 填充         #
# --------------------------------------------------------------------------- #


def test_agent_real_provider_measured_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实源命中 → provenance=measured、实测值进 facts、覆盖 LLM 推理值。"""

    _patch_llm_success(monkeypatch, _LLM_PAYLOAD)
    agent = EnvironmentAgent(
        geo_provider=_RealGeoProvider(),
        weather_provider=_RealWeatherProvider(),
    )
    ctx = AgentContext(
        request_id="env-real-hit",
        input_data={"address": "广东省汕头市", "coordinates": {"lat": 23.35, "lng": 116.68}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    # 真实源 → measured。
    assert result.data["field_provenance"]["prevailing_wind"] == "measured"
    assert result.data["field_provenance"]["geocode"] == "measured"
    # 数据源标识为真实源名。
    assert result.data["data_providers"]["weather"] == "fake-real"
    assert result.data["data_providers"]["geo"] == "fake-real-geo"
    # 实测值覆盖 LLM 推理的「东南」，facts 填充实测值。
    assert result.data["prevailing_wind"] == "SE"
    assert result.data["facts"]["prevailing_wind"] == "SE"
    assert result.data["facts"]["geocode"]["city"] == "汕头市"
    # 仍有未覆盖关键字段（climate_zone/solar 本 Sprint 无真实源）→ 顶层 pending。
    assert result.data["pending_verification"] is True


# --------------------------------------------------------------------------- #
# 降级路径：Provider 抛错 → 回落 LLM、gaps 登记、invoke 不抛异常            #
# --------------------------------------------------------------------------- #


def test_agent_failing_provider_degrades_to_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider 抛错 → ADR-03 降级：不阻断 invoke、gaps 登记、pending 保持。"""

    _patch_llm_success(monkeypatch, _LLM_PAYLOAD)
    agent = EnvironmentAgent(weather_provider=_FailingWeatherProvider())
    ctx = AgentContext(
        request_id="env-fail-degrade",
        input_data={"address": "广东省汕头市", "coordinates": {"lat": 23.35, "lng": 116.68}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True  # 绝不因数据源崩溃。
    assert any("weather_provider: fetch_failed" in g for g in result.data["gaps"])
    # 风况降级回 LLM 推理（inferred），pending 保持 True。
    assert result.data["field_provenance"]["prevailing_wind"] == "inferred"
    assert result.data["pending_verification"] is True


# --------------------------------------------------------------------------- #
# 默认配置零行为变化：全 disabled → data_providers=disabled                  #
# --------------------------------------------------------------------------- #


def test_agent_default_config_all_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无注入构造 → 按 config.yaml（默认全 disabled）构建，provider=disabled。"""

    _patch_llm_success(monkeypatch, _LLM_PAYLOAD)
    agent = EnvironmentAgent()  # 走 config.yaml，默认全 disabled
    ctx = AgentContext(
        request_id="env-default",
        input_data={"address": "广东省汕头市", "coordinates": {"lat": 23.35, "lng": 116.68}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["data_providers"] == {"geo": "disabled", "weather": "disabled"}
    assert result.data["field_provenance"]["prevailing_wind"] == "inferred"


# --------------------------------------------------------------------------- #
# 防编造锁终态：无 Provider + LLM 关闭 → 风况字段必须为「不确定」            #
# --------------------------------------------------------------------------- #


def test_anti_fabrication_lock_no_provider_no_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 Provider 且 LLM 关闭 → 风况字段不可出现任何具体合成值，恒为「不确定」。"""

    _patch_llm_disabled(monkeypatch)
    agent = EnvironmentAgent()  # 默认全 disabled
    ctx = AgentContext(
        request_id="env-lock",
        input_data={"address": "广东省汕头市", "coordinates": {"lat": 23.35, "lng": 116.68}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["provider"] == "mock"
    # 红线：没有任何具体数值流入风况字段。
    assert result.data["prevailing_wind"] == "不确定"
    assert result.data["facts"] == {}
