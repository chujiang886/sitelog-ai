"""Shared Agent contracts for the BOIP multi-Agent runtime."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


DEFAULT_PROMPT_FILENAME: str = "prompt.md"
DEFAULT_AGENT_DIR: Path = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Evidence:
    """Traceable evidence attached to an Agent request or result."""

    source: str
    observed_at: str
    confidence: str
    content: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject incomplete evidence instead of silently fabricating provenance."""

        if not self.source.strip():
            raise ValueError("Evidence source must not be empty")
        if not self.observed_at.strip():
            raise ValueError("Evidence observed_at must not be empty")
        if not self.confidence.strip():
            raise ValueError("Evidence confidence must not be empty")
        object.__setattr__(self, "content", MappingProxyType(dict(self.content)))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the evidence."""

        return {
            "source": self.source,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "content": dict(self.content),
        }


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Immutable invocation context shared across Agent boundaries."""

    request_id: str
    input_data: Mapping[str, Any] = field(default_factory=dict)
    evidence: Sequence[Evidence] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize mutable inputs so an invocation has a stable audit snapshot."""

        if not self.request_id.strip():
            raise ValueError("Agent context request_id must not be empty")
        object.__setattr__(self, "input_data", MappingProxyType(dict(self.input_data)))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def with_input(self, extra: Mapping[str, Any]) -> AgentContext:
        """Return a new context carrying additional input fields."""

        merged: dict[str, Any] = dict(self.input_data)
        merged.update(dict(extra))
        return replace(self, input_data=merged)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Standard result container for future concrete Agent implementations."""

    success: bool
    data: Mapping[str, Any] = field(default_factory=dict)
    evidence: Sequence[Evidence] = field(default_factory=tuple)
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """Freeze result data, evidence and optional error for reliable processing."""

        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.error is not None:
            object.__setattr__(self, "error", MappingProxyType(dict(self.error)))

    def to_envelope(self) -> dict[str, Any]:
        """Return the BOIP standard API envelope representation."""

        envelope: dict[str, Any] = {
            "success": self.success,
            "data": dict(self.data),
        }
        if self.evidence:
            envelope["data"]["evidence"] = [item.to_dict() for item in self.evidence]
        if self.error is not None:
            envelope["error"] = dict(self.error)
        return envelope

    @classmethod
    def placeholder(
        cls,
        *,
        agent_name: str,
        status: str,
        pending_verification: bool = True,
        extra: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        """Build a Phase 0 placeholder result carrying pending_verification evidence."""

        payload: dict[str, Any] = {
            "agent": agent_name,
            "status": status,
        }
        if extra:
            payload.update(dict(extra))
        evidence: tuple[Evidence, ...] = (
            Evidence(
                source=f"{agent_name}.invoke",
                observed_at="phase0",
                confidence=(
                    "pending_verification"
                    if pending_verification
                    else "placeholder"
                ),
                content={"status": status},
            ),
        )
        return cls(success=True, data=payload, evidence=evidence)


class BaseAgent(ABC):
    """Abstract base contract implemented by every BOIP Agent."""

    def __init__(
        self,
        name: str,
        description: str,
        version: str,
        *,
        prompt_filename: str = DEFAULT_PROMPT_FILENAME,
    ) -> None:
        """Initialize stable Agent identity metadata and prompt resolver."""

        normalized_name: str = name.strip()
        normalized_description: str = description.strip()
        normalized_version: str = version.strip()
        if not normalized_name:
            raise ValueError("Agent name must not be empty")
        if not normalized_description:
            raise ValueError("Agent description must not be empty")
        if not normalized_version:
            raise ValueError("Agent version must not be empty")
        self._name: str = normalized_name
        self._description: str = normalized_description
        self._version: str = normalized_version
        self._prompt_filename: str = prompt_filename

    @property
    def name(self) -> str:
        """Return the globally unique Agent registry name."""

        return self._name

    @property
    def description(self) -> str:
        """Return the human-readable Agent responsibility summary."""

        return self._description

    @property
    def version(self) -> str:
        """Return the Agent contract version."""

        return self._version

    @property
    def prompt_filename(self) -> str:
        """Return the configured prompt file name (defaults to prompt.md)."""

        return self._prompt_filename

    @property
    @abstractmethod
    def tools(self) -> Sequence[str]:
        """Return declared tool identifiers available to this Agent."""

        raise NotImplementedError("Concrete Agent must declare tools")

    @abstractmethod
    async def invoke(self, context: AgentContext) -> AgentResult:
        """Execute the Agent against an immutable, evidence-aware context."""

        raise NotImplementedError("Concrete Agent must implement invoke")

    # ------------------------------------------------------------------ #
    # Phase 0 helpers (added by T04) — keep T01 contract intact.         #
    # ------------------------------------------------------------------ #

    def _load_prompt(self, base_dir: Path | None = None) -> str:
        """Load the Agent prompt template from its sibling prompt.md.

        Phase 0 implementations only need the raw text to demonstrate
        contract discovery; LLM execution is intentionally disabled.
        """

        candidate_dir: Path = base_dir if base_dir is not None else self._default_prompt_dir()
        prompt_path: Path = candidate_dir / self._prompt_filename
        if not prompt_path.is_file():
            raise FileNotFoundError(
                f"Prompt file not found for Agent {self._name}: {prompt_path}"
            )
        return prompt_path.read_text(encoding="utf-8")

    def _default_prompt_dir(self) -> Path:
        """Resolve the directory holding the Agent's prompt.md file.

        Convention: agents/<group>/prompt.md sits next to agent.py.
        Subclasses may override ``_default_prompt_dir`` to relocate the lookup.
        """

        module: Any = type(self).__module__
        module_path: Path = Path(module.replace(".", "/") + ".py").resolve()
        candidate: Path = module_path.parent
        if (candidate / self._prompt_filename).is_file():
            return candidate
        # Fallback for cases where the module is loaded via loader entry-points
        return DEFAULT_AGENT_DIR

    def _validate_input(self, context: AgentContext) -> None:
        """Reject invocations missing a non-empty request_id or input payload.

        Concrete Agents may override this method to add stricter checks
        (for example, required fields per prompt.md). The base contract
        only guarantees the immutable envelope is present.
        """

        if not context.request_id.strip():
            raise ValueError(f"Agent {self._name} requires a non-empty request_id")
        if context.input_data is None:
            raise ValueError(f"Agent {self._name} requires an input payload")

    def _emit_evidence(
        self,
        *,
        source: str,
        confidence: str = "pending_verification",
        observed_at: str = "phase0",
        content: Mapping[str, Any] | None = None,
    ) -> Evidence:
        """Construct an Evidence item with sensible Phase 0 defaults."""

        return Evidence(
            source=f"{self._name}.{source}",
            observed_at=observed_at,
            confidence=confidence,
            content=dict(content or {}),
        )

    def _placeholder_result(
        self,
        *,
        status: str,
        extra: Mapping[str, Any] | None = None,
        pending_verification: bool = True,
    ) -> AgentResult:
        """Return a Phase 0 placeholder ``AgentResult`` for this Agent."""

        return AgentResult.placeholder(
            agent_name=self._name,
            status=status,
            pending_verification=pending_verification,
            extra=extra,
        )