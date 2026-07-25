"""BOIP Agent 加载器。

负责：
- 解析 agents/config.yaml 中的路由表；
- 实例化并注册所有启用的 Agent；
- 提供 ``python -m agents.loader list`` CLI 入口；
- 在 Phase 0 强制 ``llm_enabled = false``，禁止外部 LLM 调用。

设计原则（16 原则 3）：
- 不引入 LangChain / AutoGen 等 Agent 框架；
- 仅完成注册与发现，不实现业务逻辑；
- 所有真实调用保持 pending_verification。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from agents.base import BaseAgent
from agents.registry import AgentRegistry


DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parent / "config.yaml"


@dataclass(frozen=True, slots=True)
class LoadedAgent:
    """Description of an Agent instance produced by the loader."""

    name: str
    class_path: str
    enabled: bool
    stage: str
    instance: BaseAgent


@dataclass(frozen=True, slots=True)
class LoaderConfig:
    """Static configuration consumed by the loader."""

    llm_enabled: bool
    agents: tuple[LoadedAgent, ...]
    pipeline: tuple[str, ...]
    engineering_enabled: bool
    raw: Mapping[str, Any]


class AgentLoader:
    """Read ``config.yaml`` and register configured Agents."""

    def __init__(
        self,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._config_path: Path = Path(config_path)
        self._registry: AgentRegistry = registry or AgentRegistry()

    # ------------------------------------------------------------------ #
    # Public API                                                        #
    # ------------------------------------------------------------------ #

    def load_config(self) -> LoaderConfig:
        """Parse ``config.yaml`` without registering Agents yet."""

        raw: Mapping[str, Any] = self._read_yaml()
        llm_enabled_raw: Any = raw.get("llm_enabled", False)
        llm_enabled: bool = bool(llm_enabled_raw)
        if llm_enabled:
            # Phase 0 hard rule: refuse to start with LLM enabled.
            raise RuntimeError(
                "agents/config.yaml 中 llm_enabled=true 违反 Phase 0 硬约束，"
                "请保持 llm_enabled=false。"
            )

        agents_cfg: Mapping[str, Any] = raw.get("agents", {})
        loaded: list[LoadedAgent] = []
        for name, item in agents_cfg.items():
            entry: Mapping[str, Any] = item if isinstance(item, Mapping) else {}
            loaded.append(
                LoadedAgent(
                    name=str(name),
                    class_path=str(entry.get("class_path", "")),
                    enabled=bool(entry.get("enabled", False)),
                    stage=str(entry.get("stage", "")),
                    instance=None,  # type: ignore[arg-type]
                )
            )

        orchestrator_cfg: Mapping[str, Any] = raw.get("orchestrator", {})
        pipeline_cfg: Sequence[Any] = orchestrator_cfg.get("pipeline", ())
        pipeline: tuple[str, ...] = tuple(str(item) for item in pipeline_cfg)

        return LoaderConfig(
            llm_enabled=llm_enabled,
            agents=tuple(loaded),
            pipeline=pipeline,
            engineering_enabled=bool(orchestrator_cfg.get("engineering_enabled", False)),
            raw=raw,
        )

    def load_all(self) -> list[BaseAgent]:
        """Instantiate and register every enabled Agent declared in config."""

        config: LoaderConfig = self.load_config()
        registered: list[BaseAgent] = []
        for entry in config.agents:
            if not entry.enabled:
                continue
            if not entry.class_path:
                raise ValueError(
                    f"Agent {entry.name} 缺少 class_path，无法加载"
                )
            agent: BaseAgent = self._instantiate(entry.class_path)
            self._registry.register(agent)
            registered.append(agent)
        return registered

    def list_registered(self) -> list[str]:
        """Return the names currently registered with the global registry."""

        return list(self._registry.list_names())

    # ------------------------------------------------------------------ #
    # Internals                                                         #
    # ------------------------------------------------------------------ #

    def _read_yaml(self) -> Mapping[str, Any]:
        """Read and validate ``config.yaml`` from disk."""

        if not self._config_path.is_file():
            raise FileNotFoundError(
                f"Agent 配置文件不存在：{self._config_path}"
            )
        text: str = self._config_path.read_text(encoding="utf-8")
        parsed: Any = yaml.safe_load(text) or {}
        if not isinstance(parsed, Mapping):
            raise ValueError("config.yaml 顶层必须是 mapping")
        return parsed

    @staticmethod
    def _instantiate(class_path: str) -> BaseAgent:
        """Import and instantiate a class declared as ``package.module.Class``."""

        module_path, _, class_name = class_path.rpartition(".")
        if not module_path or not class_name:
            raise ValueError(
                f"class_path 格式错误：{class_path}（应为 package.module.Class）"
            )
        module = importlib.import_module(module_path)
        cls: Any = getattr(module, class_name, None)
        if cls is None:
            raise AttributeError(
                f"找不到类 {class_path}（模块 {module_path} 中无 {class_name}）"
            )
        instance: Any = cls()
        if not isinstance(instance, BaseAgent):
            raise TypeError(
                f"{class_path} 必须继承 agents.base.BaseAgent"
            )
        return instance


# ---------------------------------------------------------------------- #
# CLI                                                                    #
# ---------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="python -m agents.loader",
        description="BOIP Agent 加载器（Phase 0 占位）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出已注册 Agent 的名称。")
    sub.add_parser("dump", help="打印当前 config.yaml 内容。")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口：``python -m agents.loader list`` 或 ``dump``。"""

    parser: argparse.ArgumentParser = _build_parser()
    args: argparse.Namespace = parser.parse_args(argv)
    loader: AgentLoader = AgentLoader()
    if args.command == "list":
        loader.load_all()
        names = loader.list_registered()
        print(json.dumps({"agents": names}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "dump":
        config = loader.load_config()
        snapshot = {
            "llm_enabled": config.llm_enabled,
            "agents": [
                {
                    "name": entry.name,
                    "class_path": entry.class_path,
                    "enabled": entry.enabled,
                    "stage": entry.stage,
                }
                for entry in config.agents
            ],
            "pipeline": list(config.pipeline),
            "engineering_enabled": config.engineering_enabled,
        }
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI passthrough
    raise SystemExit(main(tuple(sys.argv[1:])))


__all__ = [
    "AgentLoader",
    "LoadedAgent",
    "LoaderConfig",
    "DEFAULT_CONFIG_PATH",
    "main",
]