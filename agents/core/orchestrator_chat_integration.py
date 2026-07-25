"""Phase 1 / T06a: LLM-Enhanced Orchestrator Router (Chat).

Extends ``CoreOrchestrator`` to support chat endpoint where:
- Loads config.yaml::llm section for dual-track endpoints
- Builds DualTrackRouter via build_router_from_config
- Dispatches messages through LLM when enabled
- Falls back gracefully when llm_enabled=false or keys are missing.

All outputs always carry pending_verification marking when
LLM backend is not connected.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OrchestratorChatResult:
    """Enriched response with double-track LLM metadata and evidence."""

    success: bool
    intent: str
    confidence: float
    llm_enabled: bool
    pending_verification: bool
    agent_steps: List[Dict[str, Any]] = field(default_factory=list)
    history_len: int = 0
    placeholder_reply: str = ""


@dataclass
class OrchestratorChatService:
    """Thin wrapper around CoreOrchestrator + DualTrackRouter.

    Phase 1 minimal correct implementation:
      - Build router from agents/config.yaml when llm.enabled=true
      - Fall back to placeholder replies otherwise (pending_verification)
      - Always return the standard {success, data} envelope
    """

    config_path: str = "agents/config.yaml"
    _router: Any = field(default=None, init=False, repr=False)
    _llm_enabled: bool = field(default=False, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            from agents.llm.router import build_router_from_config

            self._router = build_router_from_config(self.config_path)
            self._llm_enabled = self._router is not None
        except Exception:  # noqa: BLE001
            self._router = None
            self._llm_enabled = False
        self._initialized = True

    @property
    def llm_enabled(self) -> bool:
        self._ensure_initialized()
        return self._llm_enabled

    async def chat(
        self,
        user_message: str,
        history: Optional[List[Dict[str, Any]]] = None,
        intent_hint: Optional[str] = None,
    ) -> OrchestratorChatResult:
        """Process one chat turn. Returns standard envelope payload."""
        self._ensure_initialized()
        history = history or []
        intent = intent_hint or "general_query"

        if not self._llm_enabled or self._router is None:
            return OrchestratorChatResult(
                success=True,
                intent=intent,
                confidence=0.0,
                llm_enabled=False,
                pending_verification=True,
                agent_steps=[],
                history_len=len(history),
                placeholder_reply=(
                    "BOIP 智能助手：当前未接入真实 LLM（pending_verification）。"
                    "请在 .env 中填入 LLM_A_API_KEY / LLM_B_API_KEY 后"
                    "将 agents/config.yaml::llm.enabled 改为 true。"
                ),
            )

        # Real LLM path: route through DualTrackRouter.
        try:
            from agents.llm.types import LLMMessage, LLMRequest, LLMRole

            messages: List[LLMMessage] = [
                LLMMessage(role=LLMRole.SYSTEM, content="你是 BOIP AI 建筑开口设计助手。"),
            ]
            for h in history[-10:]:
                role = LLMRole(h.get("role", "user"))
                messages.append(LLMMessage(role=role, content=str(h.get("content", ""))))
            messages.append(LLMMessage(role=LLMRole.USER, content=user_message))

            request = LLMRequest(messages=messages, model="", temperature=0.2)
            response = await self._router.route(request)
            return OrchestratorChatResult(
                success=True,
                intent=intent,
                confidence=0.85,
                llm_enabled=True,
                pending_verification=False,
                agent_steps=[
                    {
                        "agent": "llm_router",
                        "ts": time.time(),
                        "finish_reason": response.finish_reason,
                    }
                ],
                history_len=len(history),
                placeholder_reply=response.content,
            )
        except Exception as exc:  # noqa: BLE001
            return OrchestratorChatResult(
                success=False,
                intent=intent,
                confidence=0.0,
                llm_enabled=True,
                pending_verification=True,
                agent_steps=[{"agent": "llm_router", "error": str(exc)}],
                history_len=len(history),
                placeholder_reply="",
            )


__all__ = ["OrchestratorChatResult", "OrchestratorChatService"]