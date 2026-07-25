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


def load_llm_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Mapping[str, Any]:
    """读取 ``llm.*`` 段；缺省返回空 dict（等价于 LLM 关闭）。

    读取后会对整个 ``llm`` 段做递归环境变量插值，使 ``${VAR:default}``
    占位符被展开。返回普通 dict，便于调用方按 ``track_a.api_key`` 取值。
    """

    path: Path = Path(config_path)
    if not path.is_file():
        return {}
    text: str = path.read_text(encoding="utf-8")
    parsed: Any = yaml.safe_load(text) or {}
    if not isinstance(parsed, Mapping):
        return {}
    llm_section: Any = parsed.get("llm", {})
    if not isinstance(llm_section, Mapping):
        return {}
    interpolated: Any = _deep_interpolate(dict(llm_section))
    return dict(interpolated)


__all__ = ["DEFAULT_CONFIG_PATH", "load_llm_config"]
