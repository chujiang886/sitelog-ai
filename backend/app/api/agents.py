"""Agent registry routes — list + placeholder invoke."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the monorepo ``agents/`` package is importable when uvicorn runs
# from inside ``backend/``. Falls back silently when running from the repo
# root (where ``agents`` is already on PYTHONPATH).
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import APIRouter, HTTPException  # noqa: E402

from agents.base import AgentContext, AgentResult  # noqa: E402
from agents.loader import AgentLoader  # noqa: E402
from agents.registry import AgentRegistry  # noqa: E402

router = APIRouter(prefix="/api/agents", tags=["agents"])


_LOADER: AgentLoader = AgentLoader()
_REGISTRY: AgentRegistry = AgentRegistry()


# Phase 0 pipeline order — kept stable so existing T02 contract tests pass.
_PHASE0_AGENT_ORDER: tuple[str, ...] = ("core", "environment", "vision", "design")


def _ensure_loaded() -> None:
    """Idempotently register the configured Agents for the running process."""

    if not _REGISTRY.list_names():
        _LOADER.load_all()


@router.get("")
async def list_agents() -> dict[str, object]:
    """Return the names registered by the Phase 0 agent registry.

    The response order mirrors the orchestration pipeline order established
    by ``04_SYSTEM_ARCHITECTURE.md`` (core → environment → vision → design).
    Any additional Agents registered later are appended in alphabetical order.
    """

    _ensure_loaded()
    registered = set(_REGISTRY.list_names())
    ordered: list[str] = [name for name in _PHASE0_AGENT_ORDER if name in registered]
    extras: list[str] = sorted(registered - set(_PHASE0_AGENT_ORDER))
    ordered.extend(extras)
    return {
        "success": True,
        "data": {"agents": ordered},
    }


@router.get("/{name}/invoke")
async def invoke_agent(
    name: str,
    request_id: str = "phase0-default",
) -> dict[str, object]:
    """Return a Phase 0 placeholder envelope for the requested Agent.

    The endpoint never invokes a real LLM. It validates that ``name`` is a
    registered Agent, builds an ``AgentContext`` and converts the returned
    ``AgentResult`` into the BOIP standard envelope.
    """

    _ensure_loaded()
    try:
        agent = _REGISTRY.get(name)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    context = AgentContext(request_id=request_id, input_data={"phase0": True})
    result: AgentResult = await agent.invoke(context)
    return result.to_envelope()