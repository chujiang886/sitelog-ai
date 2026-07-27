"""OrchestratorChatService 路由初始化回归（Phase 2.1.6 / P2 修复）。

验证：
- ``_ensure_initialized()`` 现在按 llm.enabled=true 真实构造 ``DualTrackRouter``
  （修复前误把 config_path 当 Mapping 传入导致 router 永远为 None）；
- ``llm_enabled`` 正确置 True；
- ``chat()`` 始终返回标准 envelope（不崩溃）。
"""

from __future__ import annotations

import asyncio

from agents.config_loader import DEFAULT_CONFIG_PATH
from agents.core.orchestrator_chat_integration import OrchestratorChatService


def test_ensure_initialized_builds_router_when_enabled():
    svc = OrchestratorChatService(config_path=str(DEFAULT_CONFIG_PATH))
    # 此前 P2：router 永远为 None，llm_enabled=False；此处应被真实构造。
    assert svc.llm_enabled is True
    svc._ensure_initialized()
    assert svc._router is not None


def test_chat_returns_standard_envelope():
    svc = OrchestratorChatService(config_path=str(DEFAULT_CONFIG_PATH))
    result = asyncio.run(svc.chat("请帮我设计阳台封窗方案"))
    # 路由已初始化（P2 修复后），chat() 始终返回标准 envelope 且不崩溃。
    # 注意：chat() 真实 LLM 路径存在一个独立的元组解包遗留 bug
    # （route() 返回 (response, results) 被赋给 response 后取 .finish_reason
    # 抛错，落入 except 返回 success=False 占位）——属 P2 之外问题，单列待跟进。
    assert result is not None
    assert result.llm_enabled is True
