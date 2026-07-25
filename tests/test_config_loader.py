"""T12-2：config_loader 环境变量插值测试。

验证 ``load_llm_config()`` 能展开 ``config.yaml`` 中的 ``${VAR:default}`` 占位符：
- 设置 ``LLM_A_API_KEY`` 环境变量 → ``track_a.api_key`` 取环境变量值；
- 删除该环境变量 → ``track_a.api_key`` 回落默认 ``pending_verification``；
- 其它占位（base_url / model / track_b.*）同样展开或落到默认；
- 普通字符串 / 标量（bool / int / 嵌套 dict）不受影响。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.config_loader import load_llm_config  # noqa: E402


def test_api_key_interpolated_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """设置环境变量后，track_a.api_key 应取环境变量值。"""

    monkeypatch.setenv("LLM_A_API_KEY", "secret-123")
    cfg = load_llm_config()
    assert cfg["track_a"]["api_key"] == "secret-123"


def test_api_key_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设置环境变量时，track_a.api_key 回落到默认 pending_verification。"""

    monkeypatch.delenv("LLM_A_API_KEY", raising=False)
    cfg = load_llm_config()
    assert cfg["track_a"]["api_key"] == "pending_verification"


def test_other_placeholders_interpolate_or_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """base_url / model / track_b 占位同样展开或回落默认。"""

    for var in (
        "LLM_A_BASE_URL",
        "LLM_A_MODEL",
        "LLM_B_API_KEY",
        "LLM_B_BASE_URL",
        "LLM_B_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = load_llm_config()
    assert cfg["track_a"]["base_url"] == "pending_verification"
    assert cfg["track_a"]["model"] == "pending_verification"
    assert cfg["track_b"]["api_key"] == "pending_verification"
    # 标量配置（bool / int）不应被插值影响
    assert cfg["enabled"] is True
    assert isinstance(cfg["router"]["timeout"], int)


def test_plain_values_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """非占位符的普通字符串与嵌套 dict 保持原值。"""

    monkeypatch.delenv("LLM_A_API_KEY", raising=False)
    cfg = load_llm_config()
    assert cfg["track_a"]["provider"] == "openai_compat"
    assert cfg["router"]["strategy"] == "fastest"
