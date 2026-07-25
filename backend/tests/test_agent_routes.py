"""Contract tests for the Phase 0 Agent routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_agents_returns_four_names_in_pipeline_order() -> None:
    """``GET /api/agents`` must return the four Phase 0 Agent names in pipeline order."""

    response = client.get("/api/agents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agents"] == ["core", "environment", "vision", "design"]


def test_invoke_environment_returns_envelope() -> None:
    """``GET /api/agents/environment/invoke`` must return a Phase 0 envelope."""

    response = client.get(
        "/api/agents/environment/invoke",
        params={"request_id": "req-env-2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent"] == "environment"
    assert payload["data"]["pending_verification"] is True
    assert isinstance(payload["data"]["evidence"], list)
    assert payload["data"]["evidence"]


def test_invoke_vision_returns_envelope() -> None:
    """``GET /api/agents/vision/invoke`` must return a Phase 0 envelope."""

    response = client.get(
        "/api/agents/vision/invoke",
        params={"request_id": "req-vision-2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent"] == "vision"


def test_invoke_design_returns_envelope() -> None:
    """``GET /api/agents/design/invoke`` must return a Phase 0 envelope."""

    response = client.get(
        "/api/agents/design/invoke",
        params={"request_id": "req-design-2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent"] == "design"


def test_invoke_core_returns_envelope() -> None:
    """``GET /api/agents/core/invoke`` must return a Phase 0 envelope."""

    response = client.get(
        "/api/agents/core/invoke",
        params={"request_id": "req-core-2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["agent"] == "core"


def test_invoke_unknown_agent_returns_error_envelope() -> None:
    """An unknown Agent must surface the standard error envelope."""

    response = client.get("/api/agents/phantom/invoke")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "HTTP_404"