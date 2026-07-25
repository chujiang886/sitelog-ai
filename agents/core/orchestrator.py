"""Core orchestrator skeleton (Phase 0) + chat entry point (Phase 1 / T06a).

The orchestrator mirrors the BOIP system architecture (``04_SYSTEM_ARCHITECTURE.md``) sequence:

    Environment -> Vision -> Design  

Phase 0 only registers the step list and synthesizes a placeholder envelope; real Agent invocation is intentionally disabled.

Phase 1 adds ``chat()`` for conversation scenarios.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, Evidence
from agents.registry import AgentRegistry


DEFAULT_PIPELINE: tuple[str, ...] = (
    "environment",
    "vision",
    "design",
    # "engineering" 暂未实现，先保留注释防止漂移（TD-005）
)


@dataclass(frozen=True, slots=True)
class OrchestrationStep:
    """Description of one orchestration step."""

    name: str
    status: str
    pending_verification: bool = True
    notes: tuple[str, ...] = ()


class CoreOrchestrator:
    """Phase 0 orchestrator returning a deterministic skeleton pipeline.

    Phase 1 additionally provides ``chat()`` for conversation scenarios
    where intents are extracted via the NLU pipeline before dispatching 
    placeholder steps.
    """

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        pipeline: Sequence[str] = DEFAULT_PIPELINE,
    ) -> None:
        """Bind the registry and pipeline; default to the canonical sequence."""
        self._registry: AgentRegistry = registry or AgentRegistry()
        self._pipeline: tuple[str, ...] = tuple(pipeline)

    @property
    def pipeline(self) -> tuple[str, ...]:
        """Return the immutable pipeline ordering."""
        return self._pipeline

    # ------------------------------------------------------------------ #
    # Phase 0 entries                                                     #
    # ------------------------------------------------------------------ #

    async def orchestrate(self, input_payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run the placeholder pipeline and return the standard envelope.

        The method never invokes registered Agents in Phase 0; it merely
        inspects the registry to confirm visibility and reports the
        configured step order.
        """
        registered: set[str] = set(self._registry.list_names())
        steps: list[OrchestrationStep] = []
        for name in self._pipeline:
            if name in registered:
                steps.append(
                    OrchestrationStep(
                        name=name,
                        status="pending_verification",
                        pending_verification=True,
                        notes=("phase0_skeleton_only",),
                    )
                )
            else:
                steps.append(
                    OrchestrationStep(
                        name=name,
                        status="not_registered",
                        pending_verification=True,
                        notes=("agent_not_yet_implemented",),
                    )
                )

        evidence = (
            Evidence(
                source="core.orchestrator",
                observed_at="phase0",
                confidence="pending_verification",
                content={
                    "pipeline": list(self._pipeline),
                    "registered": sorted(registered),
                },
            ),
        )

        result = AgentResult(
            success=True,
            data={
                "pipeline": [step.name for step in steps],
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "pending_verification": step.pending_verification,
                        "notes": list(step.notes),
                    }
                    for step in steps
                ],
                "pending_verification": True,
            },
            evidence=evidence,
        )
        return result.to_envelope()

    async def orchestrate_context(
        self, context: AgentContext
    ) -> AgentResult:
        """Run the pipeline against an ``AgentContext`` and return an ``AgentResult``."""
        registered: set[str] = set(self._registry.list_names())
        steps: list[OrchestrationStep] = []
        for name in self._pipeline:
            if name in registered:
                steps.append(
                    OrchestrationStep(
                        name=name,
                        status="pending_verification",
                        pending_verification=True,
                        notes=("phase0_skeleton_only",),
                    )
                )
            else:
                steps.append(
                    OrchestrationStep(
                        name=name,
                        status="not_registered",
                        pending_verification=True,
                        notes=("agent_not_yet_implemented",),
                    )
                )

        evidence = (
            Evidence(
                source="core.orchestrator",
                observed_at="phase0",
                confidence="pending_verification",
                content={
                    "request_id": context.request_id,
                    "pipeline": list(self._pipeline),
                    "registered": sorted(registered),
                },
            ),
        )
        return AgentResult(
            success=True,
            data={
                "pipeline": [step.name for step in steps],
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "pending_verification": step.pending_verification,
                        "notes": list(step.notes),
                    }
                    for step in steps
                ],
                "pending_verification": True,
            },
            evidence=evidence,
        )

    # ------------------------------------------------------------------ #
    # Phase 1 ``chat()`` entry                                            #
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        input_payload: Mapping[str, Any],
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Phase 1 / ``chat`` scenario — extract intent via NLU then dispatch placeholder sub-agent steps.

        Behavior contract:
         - Accepts ``user_message`` / ``history`` from the payload;
         - Runs ``IntentExtractor.extract_sync()`` (rule-only by default);
         - Dispatches each registered agent as a **placeholder** step;
         - Returns envelope with ``intent``, ``agent_steps``, and
           ``pending_verification`` markers.
        """
        start = time.monotonic()

        # 1) Extract intent via the NLU pipeline (rule-based)
        from agents.core.nlu import IntentExtractor

        user_message: str = str(input_payload.get("user_message", "")).strip()
        extractor = IntentExtractor()
        extracted = extractor.extract_sync(user_message)

        # 2) Build per-agent step descriptions (placeholders)
        registered: set[str] = set(self._registry.list_names())
        ordered_steps: list[str] = list(self._pipeline)
        agent_steps: list[dict[str, Any]] = []
        for name in ordered_steps:
            if name in registered:
                agent_steps.append({
                    "name": name,
                    "status": "pending_verification",
                    "pending_verification": True,
                    "notes": ("phase1_chat_placeholder",),
                })
            else:
                agent_steps.append({
                    "name": name,
                    "status": "not_registered",
                    "pending_verification": True,
                    "notes": ("agent_not_yet_implemented",),
                })

        # 3) Build envelope with NLU details
        elapsed_ms = int((time.monotonic() - start) * 1000)
        
        evidence = (
            Evidence(
                source="core.orchestrator.chat",
                observed_at="phase1",
                confidence="pending_verification",
                content={
                    "intent": extracted.intent.value,
                    "intent_confidence": extracted.confidence,
                    "method": extracted.method,
                    "matched_keywords": list(extracted.matched_keywords),
                    "history_len": len(history or ()),
                    "pipeline": ordered_steps,
                    "registered_agents": sorted(registered),
                    "elapsed_ms": elapsed_ms,
                },
            ),
        )

        return AgentResult(
            success=True,
            data={
                "intent": extracted.to_dict(),
                "pipeline": ordered_steps,
                "agent_steps": agent_steps,
                "history_len": len(history or ()),
                "pending_verification": True,
                "placeholder_reply": (
                    f"Phase 1 placeholder: intent={extracted.intent.value},"
                    f"method={extracted.method},confidence={extracted.confidence:.2f}"
                ),
            },
            evidence=evidence,
        ).to_envelope()


__all__ = [
    "DEFAULT_PIPELINE",
    "CoreOrchestrator",
    "OrchestrationStep",
]
