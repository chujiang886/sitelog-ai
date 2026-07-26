"""Vision Agent OpenAI-compatible multimodal request tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agents.llm.types import LLMRequest, LLMResponse
from agents.vision.agent import USER_PROMPT_TEMPLATE, VisionAgent


# Base64-encoded 1x1 transparent PNG.
_ONE_PIXEL_PNG_B64: str = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "/w8AAusB9Y9Z4WQAAAAASUVORK5CYII="
)


def test_call_llm_uses_openai_multimodal_content_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vision requests must send the image through an image_url content block."""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "test-key"},
            "track_b": {},
        },
    )
    captured: dict[str, Any] = {}
    response = LLMResponse(
        content=(
            '{"scene_type":"balcony","obstructions":["planter"],'
            '"orientation_hint":"south","quality":"high",'
            '"recommendations":["sun-shade"]}'
        ),
        model="HY-Vision-2.0-Instruct",
        finish_reason="stop",
    )

    async def fake_route(request: LLMRequest) -> tuple[LLMResponse, list[Any]]:
        captured["request"] = request
        return response, []

    class FakeRouter:
        """Minimal async router double that captures the outgoing request."""

        route = staticmethod(fake_route)

        async def aclose(self) -> None:
            """Mirror the production router cleanup contract."""

    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda _config: FakeRouter(),
    )

    payload, provider, pending = asyncio.run(
        VisionAgent()._call_llm(
            image_b64=_ONE_PIXEL_PNG_B64,
            mime_type="image/png",
        )
    )

    assert payload == {
        "scene_type": "balcony",
        "obstructions": ["planter"],
        "orientation_hint": "south",
        "quality": "high",
        "recommendations": ["sun-shade"],
    }
    assert provider == "HY-Vision-2.0-Instruct"
    assert pending is False

    request = captured["request"]
    assert isinstance(request, LLMRequest)
    user_content = request.messages[1].content
    assert isinstance(user_content, list)
    assert user_content[0] == {"type": "text", "text": USER_PROMPT_TEMPLATE}
    assert user_content[1] == {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{_ONE_PIXEL_PNG_B64}",
        },
    }
