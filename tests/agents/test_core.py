"""Verify the Core Agent placeholder envelope."""

from __future__ import annotations

import asyncio

from agents.base import AgentContext
from agents.core.agent import CORE_AGENT_NAME, CoreAgent


def test_core_agent_identity() -> None:
    """CoreAgent must expose the canonical name and Phase 0 version."""

    agent = CoreAgent()
    assert agent.name == CORE_AGENT_NAME
    assert agent.version.endswith("phase0")
    assert "orchestrator" in agent.description.lower() or "协调" in agent.description


def test_core_agent_invokes_with_placeholder_envelope() -> None:
    """invoke() must return an envelope-shaped AgentResult with evidence."""

    agent = CoreAgent()
    context = AgentContext(request_id="req-core-1", input_data={"foo": "bar"})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert result.data["agent"] == "core"
    assert result.data["stage"] == "core_placeholder"
    envelope = result.to_envelope()
    assert envelope["success"] is True
    assert "evidence" in envelope["data"]


def test_core_agent_rejects_empty_request_id_at_context_layer() -> None:
    """AgentContext itself rejects blank request_id at construction time."""

    with __import__("pytest").raises(ValueError):
        AgentContext(request_id="   ", input_data={})