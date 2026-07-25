"""Phase 1 / T06a: Orchestrator Chat (DEPRECATED STUB).

This module was originally planned to provide LLM-enhanced chat orchestration,
but the production path is now:

- backend/app/api/conversations.py  ->  HTTP entrypoint (chat endpoint)
- agents/core/orchestrator.py        ->  CoreAgent.chat() (sync orchestration)
- agents/core/orchestrator_chat_integration.py  ->  LLM integration layer
- agents/llm/                       ->  DualTrackRouter + providers

This file is kept only as a stub so legacy imports do not break. Do not add
new logic here. New code should go into orchestrator_chat_integration.py.
"""

from __future__ import annotations

from typing import Any


def build_llm_enhanced_router(config_path: str = "agents/config.yaml") -> Any:
    """Legacy stub. Always returns None (no LLM router wired in this path).

    Use ``agents.core.orchestrator_chat_integration.OrchestratorChatService``
    or ``agents.llm.router.build_router_from_config`` directly.
    """
    return None


__all__ = ["build_llm_enhanced_router"]