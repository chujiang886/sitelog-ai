"""BOIP LLM Provider 抽象层（Phase 1 / T06a）。

设计原则（16 原则 3 + 原则 5）：
- 自研 provider 抽象，不引入 LangChain / LiteLLM；
- 抽象类 + 双轨路由 + MockProvider 默认，确保未配置真实 key 时不崩溃；
- 所有响应携带 confidence / observed_at / source，便于证据链追踪；
- 任何未填写 API key 必须标记 ``pending_verification``。
"""

from .base import LLMProvider, LLMProviderError, LLMRouterError
from .mock import MockProvider
from .router import DualTrackRouter, RouterStrategy
from .types import LLMRequest, LLMResponse, LLMRole, LLMRouteResult

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMRouterError",
    "LLMRequest",
    "LLMResponse",
    "LLMRole",
    "LLMRouteResult",
    "MockProvider",
    "DualTrackRouter",
    "RouterStrategy",
]