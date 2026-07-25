"""Smoke test covering every Phase 0 HTTP entry point."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_phase0_api_smoke(client: TestClient, auth_token: str) -> None:
    """Health, projects, Agents, and knowledge routes must all be callable."""

    headers: dict[str, str] = {"Authorization": auth_token}
    expected_routes: tuple[tuple[str, str], ...] = (
        ("/health", "health"),
        ("/api/projects", "projects"),
        ("/api/agents", "agents"),
        ("/api/knowledge/rules", "knowledge"),
    )

    for path, route_name in expected_routes:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, f"{route_name} route failed: {response.text}"
        payload = response.json()
        assert payload["success"] is True
        assert "data" in payload
