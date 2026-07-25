"""Verify the Design Agent envelope (Phase 0 placeholder + Phase 1 LLM hook)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.design.agent import (
    DESIGN_AGENT_NAME,
    DESIGN_AGENT_VERSION,
    SYSTEM_PROMPT,
    DesignAgent,
)


# --------------------------------------------------------------------------- #
# 身份 / 协议                                                                    #
# --------------------------------------------------------------------------- #


def test_design_agent_identity() -> None:
    """DesignAgent must expose the canonical name and Phase 1 version."""

    agent = DesignAgent()
    assert agent.name == DESIGN_AGENT_NAME
    assert agent.version == DESIGN_AGENT_VERSION
    assert agent.version.startswith("1.0.0")


def test_design_agent_declares_tools() -> None:
    """tools 属性应包含 knowledge_mcp + rule_engine。"""

    agent = DesignAgent()
    tools = list(agent.tools)
    assert "knowledge_mcp" in tools
    assert "rule_engine" in tools


def test_design_agent_system_prompt_contains_schema() -> None:
    """system prompt 必须包含 candidates 与关键候选字段，避免下游 schema 漂移。"""

    assert "candidates" in SYSTEM_PROMPT
    assert "opening_type" in SYSTEM_PROMPT
    assert "frame_material" in SYSTEM_PROMPT
    assert "glass_type" in SYSTEM_PROMPT
    assert "estimated_cost_tier" in SYSTEM_PROMPT
    assert "rationale" in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# 占位 / 降级                                                                    #
# --------------------------------------------------------------------------- #


def test_design_agent_placeholder_when_all_inputs_missing() -> None:
    """视觉/环境/需求三类输入全缺 → pending_verification 占位（不杜撰设计）。"""

    agent = DesignAgent()
    context = AgentContext(request_id="req-design-1", input_data={"note": "only note"})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert result.data["agent"] == "design"
    assert result.data["pending_verification"] is True
    assert result.data["candidates"] == []
    gaps = result.data["gaps"]
    assert any("vision_result" in gap for gap in gaps)
    assert any("environment_result" in gap for gap in gaps)
    assert any("consultation" in gap for gap in gaps)
    envelope = result.to_envelope()
    assert envelope["success"] is True
    assert envelope["data"]["candidates"] == []


def test_design_agent_placeholder_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llm.enabled=false → 真实 invoke 仍返回占位，不抛错，candidates=[]。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-llm-off",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["candidates"] == []
    assert result.data["provider"] == "mock"
    assert "design_rule_engine: pending_verification" in result.data["review_required"]


def test_design_agent_returns_failed_envelope_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 抛错时返回 success=False + error.code=DESIGN_FAILED。"""

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

    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-llm-err",
        input_data={"consultation": {"budget_tier": "高端"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "DESIGN_FAILED"
    assert result.data["candidates"] == []


def test_design_agent_returns_failed_envelope_when_candidates_not_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回合法 JSON 但 candidates 非 3 项 → success=False + DESIGN_FAILED。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )

    # 只给 2 个候选，违反"恰好 3 项"约束。
    parsed_payload = {
        "candidates": [
            {
                "id": "D1",
                "title": "断桥铝平开窗方案",
                "opening_type": "平开窗",
                "frame_material": "断桥铝合金",
                "glass_type": "中空玻璃",
                "dimensions_hint": "宽 1.8m × 高 2.1m",
                "estimated_cost_tier": "标准",
                "pros": ["密封好"],
                "cons": ["造价略高"],
                "rationale": "通用推荐。",
            },
            {
                "id": "D2",
                "title": "塑钢推拉窗方案",
                "opening_type": "推拉窗",
                "frame_material": "塑钢",
                "glass_type": "单片钢化",
                "dimensions_hint": "宽 1.8m × 高 2.1m",
                "estimated_cost_tier": "经济",
                "pros": ["便宜"],
                "cons": ["易老化"],
                "rationale": "预算优先。",
            },
        ]
    }

    fake_response = SimpleNamespace(content=json.dumps(parsed_payload), model="qwen-test")

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

    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-bad-count",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "DESIGN_FAILED"


def test_design_agent_parses_valid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回合法 JSON（3 个 candidates）→ 字段透传，pending=False，长度=3。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )

    parsed_payload = {
        "candidates": [
            {
                "id": "D1",
                "title": "断桥铝平开窗方案",
                "opening_type": "平开窗",
                "frame_material": "断桥铝合金",
                "glass_type": "中空玻璃",
                "dimensions_hint": "宽 1.8m × 高 2.1m，左右等分",
                "estimated_cost_tier": "标准",
                "pros": ["密封性好", "隔音佳"],
                "cons": ["造价略高"],
                "rationale": "汕头夏热冬暖、东南风主导，平开窗气密性优。",
            },
            {
                "id": "D2",
                "title": "塑钢推拉窗方案",
                "opening_type": "推拉窗",
                "frame_material": "塑钢",
                "glass_type": "单片钢化",
                "dimensions_hint": "宽 1.8m × 高 2.1m，推拉扇",
                "estimated_cost_tier": "经济",
                "pros": ["性价比高", "不占空间"],
                "cons": ["密封性一般"],
                "rationale": "预算优先时的次选。",
            },
            {
                "id": "D3",
                "title": "木铝复合落地窗方案",
                "opening_type": "落地窗",
                "frame_material": "木铝复合",
                "glass_type": "低辐射 Low-E",
                "dimensions_hint": "宽 2.4m × 高 2.6m，整面采光",
                "estimated_cost_tier": "高端",
                "pros": ["保温优", "颜值高"],
                "cons": ["成本高", "需结构复核"],
                "rationale": "对采光与保温有高要求时考虑。",
            },
        ]
    }

    fake_response = SimpleNamespace(content=json.dumps(parsed_payload), model="qwen-test")

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

    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-llm-ok",
        input_data={
            "vision_result": {"scene_type": "落地窗", "orientation_hint": "南"},
            "environment_result": {
                "climate_zone": "夏热冬暖地区",
                "prevailing_wind": "东南",
                "solar_exposure": "西晒明显",
            },
            "consultation": {"budget_tier": "标准", "style_preference": "现代简约"},
            "address": "广东省汕头市",
            "region_hint": "华南/汕头",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is False
    candidates = result.data["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 3
    # 字段透传校验
    assert candidates[0]["id"] == "D1"
    assert candidates[0]["title"] == "断桥铝平开窗方案"
    assert candidates[0]["opening_type"] == "平开窗"
    assert candidates[0]["frame_material"] == "断桥铝合金"
    assert candidates[0]["glass_type"] == "中空玻璃"
    assert candidates[0]["estimated_cost_tier"] == "标准"
    assert candidates[0]["pros"] == ["密封性好", "隔音佳"]
    assert candidates[0]["cons"] == ["造价略高"]
    assert "汕头" in candidates[0]["rationale"]
    assert result.data["provider"] == "qwen-test"
    assert "design_rule_engine: pending_verification" in result.data["review_required"]
    assert "assumptions" in result.data and isinstance(result.data["assumptions"], list)


def test_design_malformed_single_input_returns_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """vision_result 为非 dict（如字符串）按缺失处理；三类全缺 → 占位 envelope。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = DesignAgent()
    # 仅提供非 dict 的 vision_result（被当作缺失）→ 视觉/环境/需求三类全缺 → 占位。
    ctx = AgentContext(
        request_id="design-malformed",
        input_data={"vision_result": "not-a-dict"},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["candidates"] == []
    assert any("vision_result" in gap for gap in result.data["gaps"])
