"""Verify the Environment Agent envelope (Phase 0 placeholder + Phase 1 LLM hook)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.environment.agent import (
    ENVIRONMENT_AGENT_NAME,
    ENVIRONMENT_AGENT_VERSION,
    SYSTEM_PROMPT,
    EnvironmentAgent,
)


# --------------------------------------------------------------------------- #
# 身份 / 协议                                                                    #
# --------------------------------------------------------------------------- #


def test_environment_agent_identity() -> None:
    """EnvironmentAgent must expose the canonical name and Phase 1 version."""

    agent = EnvironmentAgent()
    assert agent.name == ENVIRONMENT_AGENT_NAME
    assert agent.version == ENVIRONMENT_AGENT_VERSION
    assert agent.version.startswith("1.0.0")


def test_environment_agent_declares_tools() -> None:
    """tools 属性应包含 weather_mcp + gis_mcp。"""

    agent = EnvironmentAgent()
    tools = list(agent.tools)
    assert "weather_mcp" in tools
    assert "gis_mcp" in tools


def test_environment_agent_system_prompt_contains_schema() -> None:
    """system prompt 必须包含 7 个核心字段，避免下游 schema 漂移。"""

    assert "climate_zone" in SYSTEM_PROMPT
    assert "prevailing_wind" in SYSTEM_PROMPT
    assert "solar_exposure" in SYSTEM_PROMPT
    assert "noise_level_hint" in SYSTEM_PROMPT
    assert "regulatory_hints" in SYSTEM_PROMPT
    assert "regional_material_preference" in SYSTEM_PROMPT
    assert "summary" in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# 占位 / 降级                                                                    #
# --------------------------------------------------------------------------- #


def test_environment_agent_placeholder_when_no_address_no_vision() -> None:
    """无地址 / 无坐标 / 无视觉线索 → pending_verification 占位（不杜撰）。"""

    agent = EnvironmentAgent()
    context = AgentContext(request_id="req-env-1", input_data={"location": "shantou"})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert result.data["agent"] == "environment"
    assert result.data["pending_verification"] is True
    gaps = result.data["gaps"]
    assert any("weather_data" in gap for gap in gaps)
    assert any("gis_data" in gap for gap in gaps)
    assert "facts" in result.data and result.data["facts"] == {}
    envelope = result.to_envelope()
    assert envelope["success"] is True
    assert envelope["data"]["pending_verification"] is True


def test_environment_agent_placeholder_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llm.enabled=false → 真实 invoke 仍返回占位，不抛错，facts 为空。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = EnvironmentAgent()
    ctx = AgentContext(
        request_id="env-llm-off",
        input_data={"address": "广东省汕头市"},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["facts"] == {}
    assert result.data["provider"] == "mock"


def test_environment_agent_returns_failed_envelope_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 抛错时返回 success=False + error.code=ENVIRONMENT_FAILED。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )

    async def _fake_route(_request):
        raise RuntimeError("forced failure")

    fake_router = SimpleNamespace(route=_fake_route, aclose=lambda: asyncio.sleep(0))
    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda _cfg: fake_router,
    )

    agent = EnvironmentAgent()
    ctx = AgentContext(
        request_id="env-llm-err",
        input_data={"address": "广东省汕头市"},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "ENVIRONMENT_FAILED"


def test_environment_agent_parses_valid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回合法 JSON 时 → 真实字段透传，pending_verification=False。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )

    parsed_payload = {
        "climate_zone": "夏热冬暖地区",
        "prevailing_wind": "东南",
        "solar_exposure": "西晒明显",
        "noise_level_hint": "中",
        "regulatory_hints": ["阳台封装需符合地方管理条例", "不得影响邻居采光"],
        "regional_material_preference": "断桥铝为主",
        "summary": "汕头沿海，夏热冬暖、东南风主导、西晒明显。",
    }

    fake_response = SimpleNamespace(
        content=json.dumps(parsed_payload),
        model="qwen-test",
    )

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

    fake_router = SimpleNamespace(route=_fake_route, aclose=lambda: asyncio.sleep(0))
    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda _cfg: fake_router,
    )

    agent = EnvironmentAgent()
    ctx = AgentContext(
        request_id="env-llm-ok",
        input_data={
            "address": "广东省汕头市",
            "coordinates": {"lat": 23.35, "lng": 116.68},
            "region_hint": "华南/汕头",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is False
    assert result.data["climate_zone"] == "夏热冬暖地区"
    assert result.data["prevailing_wind"] == "东南"
    assert result.data["solar_exposure"] == "西晒明显"
    assert result.data["noise_level_hint"] == "中"
    assert result.data["regulatory_hints"] == [
        "阳台封装需符合地方管理条例",
        "不得影响邻居采光",
    ]
    assert result.data["regional_material_preference"] == "断桥铝为主"
    assert result.data["provider"] == "qwen-test"
    assert result.data["facts"]["climate_zone"] == "夏热冬暖地区"


def test_environment_non_dict_inputs_no_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """coordinates / vision_result 为非 dict（如字符串）时不应崩溃，按缺失处理返回占位。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = EnvironmentAgent()
    ctx = AgentContext(
        request_id="env-nondict",
        input_data={
            "address": "广东省汕头市",
            "coordinates": "23.35,116.68",  # 非 dict
            "vision_result": "some-string",  # 非 dict
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.data["agent"] == "environment"
    assert result.data["pending_verification"] is True
    assert result.data["provider"] == "mock"
