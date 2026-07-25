"""API contract tests for the backend health endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_standard_success_envelope() -> None:
    """The health endpoint follows the project-wide API envelope."""

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["service"] == "backend"
    assert isinstance(payload["data"]["ts"], str)
    assert payload["data"]["ts"]
