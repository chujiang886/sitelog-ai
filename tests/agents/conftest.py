"""Shared fixtures for the Agent framework tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_agent_registry() -> None:
    """Reset the singleton Agent registry between tests for isolation."""

    # Import inside the fixture so the conftest loads cleanly even when
    # pytest has not yet added the project root to ``sys.path``.
    from agents.registry import AgentRegistry

    AgentRegistry().reset()
    yield
    AgentRegistry().reset()