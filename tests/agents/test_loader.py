"""Verify AgentLoader reads config.yaml and registers Agents."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.loader import AgentLoader, DEFAULT_CONFIG_PATH
from agents.registry import AgentRegistry


def test_loader_load_all_registers_four_agents() -> None:
    """load_all() must register all four Phase 0 Agents."""

    loader = AgentLoader(config_path=DEFAULT_CONFIG_PATH, registry=AgentRegistry())
    registered = loader.load_all()
    names = sorted(agent.name for agent in registered)
    assert names == ["core", "design", "environment", "vision"]


def test_loader_rejects_llm_enabled(tmp_path: Path) -> None:
    """load_all() must refuse any config that turns llm_enabled on."""

    config = tmp_path / "config.yaml"
    config.write_text(
        "version: '0.1.0'\nllm_enabled: true\nagents: {}\norchestrator: {}\n",
        encoding="utf-8",
    )
    loader = AgentLoader(config_path=config, registry=AgentRegistry())
    with pytest.raises(RuntimeError):
        loader.load_all()


def test_loader_load_config_snapshot(tmp_path: Path) -> None:
    """load_config() must expose a structured LoaderConfig snapshot."""

    loader = AgentLoader(config_path=DEFAULT_CONFIG_PATH, registry=AgentRegistry())
    config = loader.load_config()
    assert config.llm_enabled is False
    assert config.engineering_enabled is False
    assert config.pipeline == ("environment", "vision", "design")
    enabled_names = sorted(entry.name for entry in config.agents if entry.enabled)
    assert enabled_names == ["core", "design", "environment", "vision"]


def test_loader_missing_config_raises(tmp_path: Path) -> None:
    """An absent config.yaml must raise FileNotFoundError."""

    loader = AgentLoader(config_path=tmp_path / "missing.yaml", registry=AgentRegistry())
    with pytest.raises(FileNotFoundError):
        loader.load_config()


def test_loader_invalid_class_path_raises(tmp_path: Path) -> None:
    """An unknown class_path must surface an ImportError-friendly exception."""

    config = tmp_path / "config.yaml"
    config.write_text(
        "version: '0.1.0'\n"
        "llm_enabled: false\n"
        "agents:\n"
        "  phantom:\n"
        "    class_path: does.not.exist.PhantomAgent\n"
        "    enabled: true\n"
        "    stage: unknown\n"
        "orchestrator:\n"
        "  pipeline: []\n",
        encoding="utf-8",
    )
    loader = AgentLoader(config_path=config, registry=AgentRegistry())
    with pytest.raises((ImportError, ModuleNotFoundError, AttributeError)):
        loader.load_all()