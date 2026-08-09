"""``agents/config.yaml`` 加载器（Phase 1 / T08）。

只暴露 LLM 路由所需的 ``llm.*`` 字段，避免重新实现 ``AgentLoader`` 的注册逻辑。
Agent 注册由 ``agents.loader.AgentLoader`` 维护；本文件仅作为
``agents.config.yaml::llm`` 的轻量访问入口，便于 Vision Agent /
Orchestrator 等非 loader 调用方读取 LLM 路由配置。

新增（Phase 2 / T12-2）：加载后对配置做 **环境变量插值**，把形如
``${VAR:default}``（兼容 ``${VAR}``）的占位符替换为
``os.environ.get("VAR", default)``。这样真实 key（如 ``LLM_A_API_KEY``）
可通过环境变量注入，Router 才能识别并切换到真实 provider；缺省时回落到
``default``（config.yaml 中统一为 ``pending_verification``）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parent / "config.yaml"

# 匹配 ${VAR} 或 ${VAR:default}；group(1)=变量名，group(2)=默认（可空）。
_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _interpolate_scalar(value: str) -> str:
    """把字符串里的 ``${VAR:default}`` 展开为环境变量值或默认值。"""

    def _replace(match: "re.Match[str]") -> str:
        var_name: str = match.group(1)
        default: str = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default)

    return _ENV_PATTERN.sub(_replace, value)


def _deep_interpolate(obj: Any) -> Any:
    """递归遍历 dict / list / str，对所有字符串值做环境变量插值。

    非字符串标量（bool / int / None 等）原样返回，保证 ``enabled``、
    ``timeout`` 等数值/布尔配置不被误改。
    """

    if isinstance(obj, str):
        return _interpolate_scalar(obj)
    if isinstance(obj, dict):
        return {str(k): _deep_interpolate(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_interpolate(v) for v in obj]
    return obj


def _load_section(
    section_name: str,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> Mapping[str, Any]:
    """读取 config.yaml 顶层任意段并做环境变量插值；缺省返回空 dict。"""

    path: Path = Path(config_path)
    if not path.is_file():
        return {}
    text: str = path.read_text(encoding="utf-8")
    parsed: Any = yaml.safe_load(text) or {}
    if not isinstance(parsed, Mapping):
        return {}
    section: Any = parsed.get(section_name, {})
    if not isinstance(section, Mapping):
        return {}
    interpolated: Any = _deep_interpolate(dict(section))
    return dict(interpolated)


def load_llm_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Mapping[str, Any]:
    """读取 ``llm.*`` 段；缺省返回空 dict（等价于 LLM 关闭）。

    读取后会对整个 ``llm`` 段做递归环境变量插值，使 ``${VAR:default}``
    占位符被展开。返回普通 dict，便于调用方按 ``track_a.api_key`` 取值。
    """

    return _load_section("llm", config_path)


def load_environment_data_config(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> Mapping[str, Any]:
    """读取 ``environment_data.*`` 段（Phase 2.2 / 2.2.1，ADR-2.2.1）。

    缺省返回空 dict（等价于全部 Provider disabled，Agent 行为零变化）。
    """

    return _load_section("environment_data", config_path)


def load_verified_thresholds(
    path: Path | str | None = None,
) -> Mapping[str, Any]:
    """读取 Design 已签字阈值库（Phase 2.2 / 2.2.2，设计 §五）。

    缺省指向 ``agents/design/thresholds/verified.json``；文件缺失 / 解析失败
    → 返回空 dict（等价全 ``pending_verification``），合入即零行为变化。
    实际解析逻辑委托 ``agents.design.threshold_loader``，本函数仅作 SSOT
    入口（与 ``load_environment_data_config`` 对称）。
    """

    from agents.design.threshold_loader import (  # noqa: PLC0415
        DEFAULT_VERIFIED_PATH,
        load_verified_thresholds as _load,
    )

    target: Path = (
        Path(path) if path is not None else DEFAULT_VERIFIED_PATH
    )
    return _load(target)


def load_engineering_enabled(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> bool:
    """读取 ``orchestrator.engineering_enabled`` 开关（Phase 3.1 Sprint A 红线）。

    缺省返回 ``False``（等价工程审核链未启用）。该开关是 Engineering 审核
    是否允许输出 ``engineering_approved`` 的最终闸门；Sprint A 期间恒为
    ``False``，任何双签阈值都不会使系统产出工程审核通过态。
    """

    section: Mapping[str, Any] = _load_section("orchestrator", config_path)
    return bool(section.get("engineering_enabled", False))


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_environment_data_config",
    "load_llm_config",
    "load_verified_thresholds",
    "load_engineering_enabled",
]
