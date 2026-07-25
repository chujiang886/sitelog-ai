"""Async contract tests for Phase 0 route and error envelopes."""

import asyncio
from collections.abc import Awaitable
from typing import Any

import httpx

from app.main import app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    """Execute a request against the ASGI app without opening a socket."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


def _run(coro: Awaitable[httpx.Response]) -> httpx.Response:
    """Run an async request in a synchronous pytest test."""

    return asyncio.run(coro)


def test_projects_returns_empty_page() -> None:
    """Projects route returns a successful empty page."""

    response = _run(_get("/api/projects"))
    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"items": [], "total": 0}}


def test_agents_returns_registry() -> None:
    """Agents route returns all registered agent names."""

    response = _run(_get("/api/agents"))
    assert response.status_code == 200
    assert response.json()["data"]["agents"] == ["core", "environment", "vision", "design"]


def test_knowledge_rules_returns_empty_page() -> None:
    """Knowledge rules route returns an empty page."""

    response = _run(_get("/api/knowledge/rules"))
    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"items": [], "total": 0}}


def test_health_returns_success_envelope() -> None:
    """Health route remains available alongside the new API routes."""

    response = _run(_get("/health"))
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_missing_route_returns_error_envelope() -> None:
    """Unknown routes are converted from FastAPI's default error shape."""

    response = _run(_get("/api/not-registered"))
    assert response.status_code == 404
    payload: dict[str, Any] = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "HTTP_404"
    assert isinstance(payload["error"]["message"], str)
