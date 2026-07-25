"""Verify the Core Orchestrator skeleton pipeline."""

from __future__ import annotations

import asyncio

from agents.base import AgentContext
from agents.core.agent import CoreAgent
from agents.core.orchestrator import DEFAULT_PIPELINE, CoreOrchestrator
from agents.environment.agent import EnvironmentAgent
from agents.registry import AgentRegistry
from agents.vision.agent import VisionAgent


def test_default_pipeline_order() -> None:
    """DEFAULT_PIPELINE must reflect environment → vision → design → engineering."""

    assert DEFAULT_PIPELINE[0] == "environment"
    assert "vision" in DEFAULT_PIPELINE
    assert "design" in DEFAULT_PIPELINE


def test_orchestrator_returns_envelope() -> None:
    """orchestrate() must return a dict with success and a pipeline list."""

    registry = AgentRegistry()
    registry.register(CoreAgent())
    registry.register(EnvironmentAgent())
    registry.register(VisionAgent())

    orchestrator = CoreOrchestrator(registry=registry)
    envelope = asyncio.run(orchestrator.orchestrate({"location": "shantou"}))
    assert envelope["success"] is True
    assert envelope["data"]["pipeline"] == list(DEFAULT_PIPELINE)
    steps = envelope["data"]["steps"]
    names = [step["name"] for step in steps]
    assert "environment" in names
    assert "vision" in names
    assert "design" in names


def test_orchestrator_flags_missing_agents() -> None:
    """orchestrator must flag steps whose target Agent is not registered."""

    registry = AgentRegistry()  # empty
    orchestrator = CoreOrchestrator(registry=registry)
    envelope = asyncio.run(orchestrator.orchestrate({}))
    steps = envelope["data"]["steps"]
    missing = {step["name"] for step in steps if step["status"] == "not_registered"}
    assert {"environment", "vision", "design"}.issubset(missing)


def test_orchestrator_context_returns_agent_result() -> None:
    """orchestrate_context() must return an AgentResult carrying evidence."""

    registry = AgentRegistry()
    registry.register(EnvironmentAgent())
    orchestrator = CoreOrchestrator(registry=registry)
    context = AgentContext(request_id="req-orch-1", input_data={"location": "shantou"})
    result = asyncio.run(orchestrator.orchestrate_context(context))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.evidence  # at least one evidence item