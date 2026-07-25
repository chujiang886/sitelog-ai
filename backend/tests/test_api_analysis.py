"""T14-2：三 Agent 分析链路端点测试。

验证 ``POST /api/analysis/run``：
- 传 address + 空 consultation → 200，响应 JSON 含 vision/environment/design 三段（即使都是 pending_verification 占位），且三段均为 dict；
- 预置 vision_result 时跳过 Vision Agent，仍聚合出三段的占位结构。

为不依赖真实 LLM / 外部服务，monkeypatch ``load_llm_config`` 返回
``enabled=False``，使三 Agent 走干净的 pending_verification 占位路径。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _disable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 LLM 关闭，确保三 Agent 走占位降级、绝不连外部。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )


def test_analysis_run_returns_three_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """address + 空 consultation → 三段均为 dict，整体 pending_verification=True。"""

    _disable_llm(monkeypatch)
    resp = client.post(
        "/api/analysis/run",
        json={
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "consultation": {},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["vision"], dict)
    assert isinstance(data["environment"], dict)
    assert isinstance(data["design"], dict)
    assert data["pending_verification"] is True
    assert isinstance(data["gaps"], list)


def test_analysis_run_with_preset_vision_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预置 vision_result 跳过 Vision Agent，仍聚合出三段 dict。"""

    _disable_llm(monkeypatch)
    resp = client.post(
        "/api/analysis/run",
        json={
            "address": "广东省汕头市",
            "vision_result": {
                "scene_type": "开放阳台",
                "orientation_hint": "东南",
                "pending_verification": True,
            },
            "consultation": {"budget_tier": "标准"},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["vision"], dict)
    assert isinstance(data["environment"], dict)
    assert isinstance(data["design"], dict)
    assert data["pending_verification"] is True


def test_analysis_run_empty_body_returns_three_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完全空 body {} → 仍返回三段占位 dict + pending_verification=True（不崩）。"""

    _disable_llm(monkeypatch)
    resp = client.post("/api/analysis/run", json={})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["vision"], dict)
    assert isinstance(data["environment"], dict)
    assert isinstance(data["design"], dict)
    assert data["pending_verification"] is True
    assert isinstance(data["gaps"], list)


def test_analysis_run_coordinates_only_returns_three_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """仅传 coordinates + region_hint（无 address）→ 三段仍为 dict，链路不崩。"""

    _disable_llm(monkeypatch)
    resp = client.post(
        "/api/analysis/run",
        json={
            "coordinates": {"lat": 23.35, "lng": 116.68},
            "region_hint": "华南沿海",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["vision"], dict)
    assert isinstance(data["environment"], dict)
    assert isinstance(data["design"], dict)
    assert data["pending_verification"] is True
