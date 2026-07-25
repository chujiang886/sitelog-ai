"""Thread-safe singleton registry for BOIP Agents."""

from __future__ import annotations

from threading import RLock
from typing import ClassVar

from .base import BaseAgent


class AgentRegistry:
    """Store one Agent instance per unique name for runtime discovery."""

    _instance: ClassVar[AgentRegistry | None] = None
    _instance_lock: ClassVar[RLock] = RLock()
    _agents: dict[str, BaseAgent]
    _registry_lock: RLock

    def __new__(cls) -> AgentRegistry:
        """Return the single process-wide registry instance."""

        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._agents = {}
                cls._instance._registry_lock = RLock()
            return cls._instance

    def register(self, agent: BaseAgent) -> None:
        """Register an Agent, rejecting accidental name collisions."""

        if not isinstance(agent, BaseAgent):
            raise TypeError("Only BaseAgent instances can be registered")
        with self._registry_lock:
            if agent.name in self._agents:
                raise ValueError(f"Agent already registered: {agent.name}")
            self._agents[agent.name] = agent

    def unregister(self, name: str) -> None:
        """Remove a previously registered Agent (used by tests for isolation)."""

        normalized_name: str = name.strip()
        if not normalized_name:
            raise ValueError("Agent name must not be empty")
        with self._registry_lock:
            if normalized_name not in self._agents:
                raise KeyError(f"Agent is not registered: {normalized_name}")
            self._agents.pop(normalized_name, None)

    def reset(self) -> None:
        """Clear all registered Agents — only intended for test isolation."""

        with self._registry_lock:
            self._agents.clear()

    def get(self, name: str) -> BaseAgent:
        """Return a registered Agent or raise a descriptive lookup error."""

        normalized_name: str = name.strip()
        if not normalized_name:
            raise ValueError("Agent name must not be empty")
        with self._registry_lock:
            try:
                return self._agents[normalized_name]
            except KeyError as error:
                raise KeyError(f"Agent is not registered: {normalized_name}") from error

    def list_all(self) -> tuple[BaseAgent, ...]:
        """Return a deterministic snapshot ordered by Agent name."""

        with self._registry_lock:
            return tuple(self._agents[name] for name in sorted(self._agents))

    def list_names(self) -> tuple[str, ...]:
        """Return a deterministic snapshot of registered Agent names."""

        with self._registry_lock:
            return tuple(sorted(self._agents))

    def has(self, name: str) -> bool:
        """Return ``True`` when an Agent with ``name`` is registered."""

        normalized_name: str = name.strip()
        if not normalized_name:
            return False
        with self._registry_lock:
            return normalized_name in self._agents