"""T14-2：三 Agent 分析链路端点测试（RBAC 改造后）。

验证 ``POST /api/analysis/run``：
- 传 address + 空 consultation → 200，响应 JSON 含 vision/environment/design 三段（即使都是 pending_verification 占位），且三段均为 dict；
- 预置 vision_result 时跳过 Vision Agent，仍聚合出三段的占位结构；
- 鉴权：无 token → 401；viewer 缺 analysis:create → 403 明确信息。

为不依赖真实 LLM / 外部服务，monkeypatch ``load_llm_config`` 返回
``enabled=False``，使三 Agent 走干净的 pending_verification 占位路径。

鉴权改造（2.2.6）：端点受 ``require_permission("analysis:create")`` 保护，
测试统一通过 ``rbac_env`` fixture 携带 JWT Bearer token。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _disable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 LLM 关闭，确保三 Agent 走占位降级、绝不连外部。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_analysis_run_returns_three_segments(
    rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """address + 空 consultation → 三段均为 dict，整体 pending_verification=True。"""

    _disable_llm(monkeypatch)
    client: TestClient = rbac_env["client"]
    resp = client.post(
        "/api/analysis/run",
        json={
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "consultation": {},
        },
        headers=_headers(rbac_env["admin_a_token"]),
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
    rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """预置 vision_result 跳过 Vision Agent，仍聚合出三段 dict。"""

    _disable_llm(monkeypatch)
    client: TestClient = rbac_env["client"]
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
        headers=_headers(rbac_env["admin_a_token"]),
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
    rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完全空 body {} → 仍返回三段占位 dict + pending_verification=True（不崩）。"""

    _disable_llm(monkeypatch)
    client: TestClient = rbac_env["client"]
    resp = client.post(
        "/api/analysis/run",
        json={},
        headers=_headers(rbac_env["admin_a_token"]),
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


def test_analysis_run_coordinates_only_returns_three_segments(
    rbac_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """仅传 coordinates + region_hint（无 address）→ 三段仍为 dict，链路不崩。"""

    _disable_llm(monkeypatch)
    client: TestClient = rbac_env["client"]
    resp = client.post(
        "/api/analysis/run",
        json={
            "coordinates": {"lat": 23.35, "lng": 116.68},
            "region_hint": "华南沿海",
        },
        headers=_headers(rbac_env["admin_a_token"]),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    data = payload["data"]
    assert isinstance(data["vision"], dict)
    assert isinstance(data["environment"], dict)
    assert isinstance(data["design"], dict)
    assert data["pending_verification"] is True


def test_analysis_run_without_token_rejected(rbac_env) -> None:
    """未携带 token → 401（受保护 API 必须失败）。"""

    client: TestClient = rbac_env["client"]
    resp = client.post("/api/analysis/run", json={"address": "汕头"})
    assert resp.status_code == 401


def test_analysis_run_viewer_forbidden(rbac_env) -> None:
    """viewer 缺 analysis:create → 403 明确信息（权限不足必须明确返回）。"""

    client: TestClient = rbac_env["client"]
    resp = client.post(
        "/api/analysis/run",
        json={"address": "汕头"},
        headers=_headers(rbac_env["viewer_a_token"]),
    )
    assert resp.status_code == 403
    assert (
        "Permission denied: requires 'analysis:create'"
        in resp.json()["error"]["message"]
    )
