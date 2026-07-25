"""Verify the Vision Agent envelope (Phase 0 placeholder + Phase 1 LLM hook)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.vision.agent import (
    SYSTEM_PROMPT,
    VISION_AGENT_NAME,
    VISION_AGENT_VERSION,
    VisionAgent,
    vision_result_from_image,
)
from agents.vision.image_processor import process_image


# --------------------------------------------------------------------------- #
# 身份 / 协议                                                                    #
# --------------------------------------------------------------------------- #


def test_vision_agent_identity() -> None:
    """VisionAgent must expose the canonical name and Phase 1 version."""

    agent = VisionAgent()
    assert agent.name == VISION_AGENT_NAME
    assert agent.version == VISION_AGENT_VERSION
    assert agent.version.startswith("1.0.0")


def test_vision_agent_declares_tools() -> None:
    """tools 属性应包含 vision_model + file_storage。"""

    agent = VisionAgent()
    tools = list(agent.tools)
    assert "vision_model" in tools
    assert "file_storage" in tools


def test_vision_agent_system_prompt_contains_schema() -> None:
    """system prompt 必须包含 5 个核心字段，避免下游 schema 漂移。"""

    assert "scene_type" in SYSTEM_PROMPT
    assert "obstructions" in SYSTEM_PROMPT
    assert "orientation_hint" in SYSTEM_PROMPT
    assert "quality" in SYSTEM_PROMPT
    assert "recommendations" in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# 占位 / 降级                                                                    #
# --------------------------------------------------------------------------- #


def test_vision_agent_invokes_with_placeholder_envelope() -> None:
    """无图调用 → pending_verification 占位（不杜撰结果）。"""

    agent = VisionAgent()
    context = AgentContext(request_id="req-vision-1", input_data={"file": "stub"})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert result.data["agent"] == "vision"
    assert result.data["scene_type"] == "unknown"
    assert result.data["pending_verification"] is True
    gaps = result.data["gaps"]
    assert any("vision_call" in gap for gap in gaps)
    envelope = result.to_envelope()
    assert envelope["success"] is True


def test_vision_agent_placeholder_when_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """llm.enabled=false → 真实 invoke 仍返回占位，不抛错。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = VisionAgent()
    ctx = AgentContext(
        request_id="vision-llm-off",
        input_data={
            "image_id": "x",
            "image_b64": "ZmFrZQ==",
            "mime_type": "image/jpeg",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True


def test_vision_agent_returns_failed_envelope_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 抛错时返回 success=false + error.code=VISION_FAILED。"""

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

    agent = VisionAgent()
    ctx = AgentContext(
        request_id="vision-llm-err",
        input_data={
            "image_id": "x",
            "image_b64": "ZmFrZQ==",
            "mime_type": "image/jpeg",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "VISION_FAILED"


def test_vision_agent_parses_valid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 返回合法 JSON 时 → 真实字段透传，pending_verification=false。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )

    parsed_payload = {
        "scene_type": "开放阳台",
        "obstructions": ["空调外机", "晾衣架"],
        "orientation_hint": "南",
        "quality": "high",
        "recommendations": ["增加遮阳帘", "检查栏杆牢固度"],
    }

    fake_response = SimpleNamespace(
        content=json.dumps(parsed_payload),
        model="qwen-test",
    )

    async def _fake_route(_request):
        return fake_response, [SimpleNamespace(provider_name="track_a", track="track_a", response=fake_response, error=None, latency_ms=1, pending_verification=False)]

    fake_router = SimpleNamespace(route=_fake_route, aclose=lambda: asyncio.sleep(0))
    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda _cfg: fake_router,
    )

    agent = VisionAgent()
    ctx = AgentContext(
        request_id="vision-llm-ok",
        input_data={
            "image_id": "x",
            "image_b64": "ZmFrZQ==",
            "mime_type": "image/jpeg",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is False
    assert result.data["scene_type"] == "开放阳台"
    assert result.data["obstructions"] == ["空调外机", "晾衣架"]
    assert result.data["provider"] == "qwen-test"


# --------------------------------------------------------------------------- #
# image_processor                                                              #
# --------------------------------------------------------------------------- #


def test_process_image_known_mime_and_size() -> None:
    """合法 JPEG → sha256/base64/extension 正确填充。"""

    content = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"X" * 64 + bytes([0xFF, 0xD9])
    processed = process_image(
        content=content, filename="a.jpg", mime_type="image/jpeg"
    )
    assert processed.mime_type == "image/jpeg"
    assert processed.extension == "jpg"
    assert processed.size_bytes == len(content)
    assert processed.sha256
    assert processed.base64


def test_process_image_rejects_bad_mime() -> None:
    from agents.vision.image_processor import ImageValidationError

    with pytest.raises(ImageValidationError):
        process_image(
            content=b"x", filename="a.gif", mime_type="image/gif"
        )


def test_process_image_rejects_empty() -> None:
    from agents.vision.image_processor import ImageValidationError

    with pytest.raises(ImageValidationError):
        process_image(
            content=b"", filename="a.jpg", mime_type="image/jpeg"
        )


# --------------------------------------------------------------------------- #
# helper                                                                       #
# --------------------------------------------------------------------------- #


def test_vision_result_from_image_helper() -> None:
    processed = process_image(
        content=b"\xff\xd8\xff\xe0abc\xff\xd9", filename="x.jpg", mime_type="image/jpeg"
    )
    payload = vision_result_from_image(processed)
    assert payload["image_b64"] == processed.base64
    assert payload["mime_type"] == "image/jpeg"
    assert isinstance(payload["image_id"], str)