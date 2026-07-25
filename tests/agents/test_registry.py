"""Verify AgentRegistry thread-safe singleton + register/get/list APIs."""

from __future__ import annotations

import pytest

from agents.base import AgentContext, AgentResult, BaseAgent
from agents.registry import AgentRegistry


class _Alpha(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="alpha", description="Alpha", version="0.0.1")

    @property
    def tools(self) -> tuple[str, ...]:
        return ()

    async def invoke(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, data={"agent": self.name})


class _Beta(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="beta", description="Beta", version="0.0.1")

    @property
    def tools(self) -> tuple[str, ...]:
        return ()

    async def invoke(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, data={"agent": self.name})


def test_registry_is_singleton() -> None:
    """Calling the constructor twice must yield the same instance."""

    a = AgentRegistry()
    b = AgentRegistry()
    assert a is b


def test_register_rejects_duplicates() -> None:
    """register() must reject duplicate names to avoid silent overrides."""

    AgentRegistry().register(_Alpha())
    with pytest.raises(ValueError):
        AgentRegistry().register(_Alpha())


def test_register_rejects_non_baseagent() -> None:
    """register() must reject objects that do not inherit from BaseAgent."""

    with pytest.raises(TypeError):
        AgentRegistry().register("not-an-agent")  # type: ignore[arg-type]


def test_get_returns_registered_agent() -> None:
    """get() must return the same instance that was registered."""

    registry = AgentRegistry()
    alpha = _Alpha()
    registry.register(alpha)
    assert registry.get("alpha") is alpha


def test_get_unknown_raises_keyerror() -> None:
    """get() must surface a descriptive KeyError when missing."""

    with pytest.raises(KeyError):
        AgentRegistry().get("missing")


def test_list_all_is_sorted_snapshot() -> None:
    """list_all() must return a sorted tuple of registered Agents."""

    registry = AgentRegistry()
    registry.register(_Beta())
    registry.register(_Alpha())
    snapshot = registry.list_all()
    assert [agent.name for agent in snapshot] == ["alpha", "beta"]


def test_list_names_matches_list_all() -> None:
    """list_names() must mirror list_all() ordering without instances."""

    registry = AgentRegistry()
    registry.register(_Beta())
    registry.register(_Alpha())
    assert registry.list_names() == ("alpha", "beta")


def test_has_reports_membership() -> None:
    """has() must return True only for registered names."""

    registry = AgentRegistry()
    registry.register(_Alpha())
    assert registry.has("alpha") is True
    assert registry.has("beta") is False
    assert registry.has("") is False


def test_unregister_removes_agent() -> None:
    """unregister() must remove a previously registered Agent."""

    registry = AgentRegistry()
    registry.register(_Alpha())
    registry.unregister("alpha")
    with pytest.raises(KeyError):
        registry.get("alpha")


def test_reset_clears_all() -> None:
    """reset() must clear every registered Agent (used by tests only)."""

    registry = AgentRegistry()
    registry.register(_Alpha())
    registry.register(_Beta())
    registry.reset()
    assert registry.list_names() == ()