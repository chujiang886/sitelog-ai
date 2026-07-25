"""Core Agent implementation skeleton (Phase 0).

The Core Agent is the orchestrator of the BOIP multi-Agent runtime.
Phase 0 provides only the registration contract and a placeholder
``invoke`` implementation; real orchestration logic lives in
``agents.core.orchestrator`` and is wired up by ``agents.loader``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from agents.base import AgentContext, AgentResult, BaseAgent


CORE_AGENT_NAME: str = "core"
CORE_AGENT_VERSION: str = "0.1.0-phase0"
CORE_AGENT_DESCRIPTION: str = (
    "BOIP 总协调 Agent：解析请求、调度专业 Agent、汇总结构化结果。"
)
_CORE_PROMPT_DIR: Path = Path(__file__).resolve().parent


class CoreAgent(BaseAgent):
    """Orchestrator Agent that fronts the BOIP multi-Agent runtime."""

    def __init__(self) -> None:
        super().__init__(
            name=CORE_AGENT_NAME,
            description=CORE_AGENT_DESCRIPTION,
            version=CORE_AGENT_VERSION,
        )

    @property
    def tools(self) -> Sequence[str]:
        """Return the declared tool identifiers used by the Core Agent."""

        return ("registry.lookup", "orchestrator.placeholder")

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Core Agent package."""

        return _CORE_PROMPT_DIR

    async def invoke(self, context: AgentContext) -> AgentResult:
        """Return a Phase 0 placeholder result for the Core Agent.

        The real orchestration is implemented by
        ``agents.core.orchestrator.CoreOrchestrator``. ``CoreAgent.invoke``
        only validates the envelope and returns a structured placeholder so
        that HTTP smoke tests have a stable response shape.
        """

        self._validate_input(context)
        self._load_prompt()  # contract check — must be discoverable
        evidence = (
            self._emit_evidence(
                source="invoke",
                content={
                    "request_id": context.request_id,
                    "stage": "core_placeholder",
                },
            ),
        )
        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "core_placeholder",
                "message": "Core Agent Phase 0 占位；真实编排请走 orchestrator.orchestrate",
            },
            evidence=evidence,
        )


__all__ = ["CORE_AGENT_NAME", "CORE_AGENT_VERSION", "CoreAgent"]